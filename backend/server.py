from fastapi import FastAPI, APIRouter, HTTPException, Depends, Response, Request, Cookie, Header, Query
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional
import uuid
from datetime import datetime, timezone, timedelta
import requests
import httpx
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import asyncio
from concurrent.futures import ThreadPoolExecutor
import re

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Trello Configuration
TRELLO_API_KEY = os.environ.get('TRELLO_API_KEY')
TRELLO_TOKEN = os.environ.get('TRELLO_TOKEN')
TRELLO_BOARD_ID = os.environ.get('TRELLO_BOARD_ID')
TRELLO_BASE_URL = "https://api.trello.com/1"

# Email Configuration
SMTP_HOST = os.environ.get('SMTP_HOST')
SMTP_PORT = int(os.environ.get('SMTP_PORT', 587))
SMTP_USER = os.environ.get('SMTP_USER')
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD')
SMTP_FROM_EMAIL = os.environ.get('SMTP_FROM_EMAIL')
SMTP_FROM_NAME = os.environ.get('SMTP_FROM_NAME', 'Sistema de Exames')

# Admin Configuration
ADMIN_EMAILS = os.environ.get('ADMIN_EMAILS', '').split(',')
ADMIN_EMAILS = [email.strip().lower() for email in ADMIN_EMAILS if email.strip()]

# Thread pool for sending emails
email_executor = ThreadPoolExecutor(max_workers=3)

# Create the main app without a prefix
app = FastAPI()

# Configure CORS origins. If ALLOWED_ORIGINS env var exists, parse it as comma-separated list.
# Otherwise, allow localhost dev origins by default. This lets frontend hosted on Vercel/Netlify
# set REACT_APP_BACKEND_URL and the backend accept cross-origin requests.
allowed = os.environ.get('ALLOWED_ORIGINS')
if allowed:
    # split and strip
    allow_list = [o.strip() for o in allowed.split(',') if o.strip()]
else:
    allow_list = []

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_list,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+$)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Cookie configuration (allow non-secure cookie in local dev if needed)
COOKIE_SECURE = os.environ.get('COOKIE_SECURE', 'true').lower() == 'true'

# Trello configuration (already declared above), quick validator
def _require_trello_env():
    missing = []
    if not os.environ.get('TRELLO_API_KEY'):
        missing.append('TRELLO_API_KEY')
    if not os.environ.get('TRELLO_TOKEN'):
        missing.append('TRELLO_TOKEN')
    if not os.environ.get('TRELLO_BOARD_ID'):
        missing.append('TRELLO_BOARD_ID')
    if missing:
        raise HTTPException(status_code=500, detail=f"Trello env missing: {', '.join(missing)}")

# ==================== MODELS ====================

class User(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    email: str
    name: str
    picture: Optional[str] = None
    department: Optional[str] = None  # "DP" or "RH"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class UserSession(BaseModel):
    user_id: str
    session_token: str
    expires_at: datetime
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    # When an ADMIN is temporarily acting as a sector (DP/RH), we store it here
    impersonate_department: Optional[str] = None  # "DP" or "RH"

class DepartmentSelection(BaseModel):
    department: str  # "DP" or "RH"

class ExamRequest(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    matricula: str
    nome: str
    data_desligamento: str  # Format: YYYY-MM-DD
    status: str = "CRIADO"  # CRIADO, EM_AGENDAMENTO, AGUARDANDO_RESULTADO, APTO, INAPTO, FINALIZADO
    trello_card_id: Optional[str] = None
    trello_card_url: Optional[str] = None
    created_by: str  # User ID
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    data_agendamento: Optional[str] = None
    observacoes: Optional[str] = None

class ExamRequestCreate(BaseModel):
    matricula: str
    nome: str
    data_desligamento: str

class ExamRequestUpdate(BaseModel):
    status: Optional[str] = None
    data_agendamento: Optional[str] = None
    observacoes: Optional[str] = None

class UserUpdate(BaseModel):
    department: str  # "DP", "RH", or "ADMIN"

class DevLoginRequest(BaseModel):
    email: str
    name: str
    department: Optional[str] = None  # optional; defaults to existing or None

# ==================== TRELLO SERVICE ====================

class TrelloService:
    def __init__(self):
        self.api_key = TRELLO_API_KEY
        self.token = TRELLO_TOKEN
        self.board_id = TRELLO_BOARD_ID
        self.base_url = TRELLO_BASE_URL
        self.lists = {}  # Cache for list IDs
    
    async def get_lists(self):
        """Get all lists from the board"""
        if self.lists:
            return self.lists
        
        try:
            url = f"{self.base_url}/boards/{self.board_id}/lists"
            params = {"key": self.api_key, "token": self.token}
            
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                
                lists_data = response.json()
                for list_item in lists_data:
                    self.lists[list_item['name']] = list_item['id']
                
                logger.info(f"Trello lists loaded: {self.lists}")
                return self.lists
        except Exception as e:
            logger.error(f"Error getting Trello lists: {e}")
            return {}
    
    async def create_card(self, name: str, description: str, list_name: str = "Novas Solicitações DP"):
        """Create a card in Trello"""
        try:
            lists = await self.get_lists()
            list_id = lists.get(list_name)
            
            if not list_id:
                logger.error(f"List '{list_name}' not found in board")
                return None
            
            url = f"{self.base_url}/cards"
            params = {
                "key": self.api_key,
                "token": self.token,
                "idList": list_id,
                "name": name,
                "desc": description
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.post(url, params=params)
                response.raise_for_status()
                
                card_data = response.json()
                logger.info(f"Card created: {card_data['id']}")
                return card_data
        except Exception as e:
            logger.error(f"Error creating Trello card: {e}")
            return None
    
    async def move_card(self, card_id: str, list_name: str):
        """Move a card to a different list"""
        try:
            lists = await self.get_lists()
            list_id = lists.get(list_name)
            
            if not list_id:
                logger.error(f"List '{list_name}' not found in board")
                return False
            
            url = f"{self.base_url}/cards/{card_id}"
            params = {
                "key": self.api_key,
                "token": self.token,
                "idList": list_id
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.put(url, params=params)
                response.raise_for_status()
                
                logger.info(f"Card {card_id} moved to {list_name}")
                return True
        except Exception as e:
            logger.error(f"Error moving Trello card: {e}")
            return False
    
    async def update_card(self, card_id: str, name: Optional[str] = None, description: Optional[str] = None):
        """Update card information"""
        try:
            url = f"{self.base_url}/cards/{card_id}"
            params = {"key": self.api_key, "token": self.token}
            
            if name:
                params["name"] = name
            if description:
                params["desc"] = description
            
            async with httpx.AsyncClient() as client:
                response = await client.put(url, params=params)
                response.raise_for_status()
                
                logger.info(f"Card {card_id} updated")
                return True
        except Exception as e:
            logger.error(f"Error updating Trello card: {e}")
            return False

    async def get_labels(self):
        """Return all labels for the configured board."""
        try:
            url = f"{self.base_url}/boards/{self.board_id}/labels"
            params = {"key": self.api_key, "token": self.token}
            async with httpx.AsyncClient() as client:
                r = await client.get(url, params=params)
                r.raise_for_status()
                return r.json()
        except Exception as e:
            logger.error(f"Error fetching labels: {e}")
            return []

    async def create_label_if_missing(self, name: str, color: str):
        """Create a board label with given name and color if it doesn't exist. Returns label object."""
        try:
            labels = await self.get_labels()
            # Match by name and color if possible
            for l in labels:
                if (l.get('name') or '').lower() == (name or '').lower() and (l.get('color') or '') == (color or ''):
                    return l

            url = f"{self.base_url}/labels"
            params = {"key": self.api_key, "token": self.token, "idBoard": self.board_id, "name": name, "color": color}
            async with httpx.AsyncClient() as client:
                r = await client.post(url, params=params)
                r.raise_for_status()
                lbl = r.json()
                logger.info(f"Created label: {lbl.get('id')} name={name} color={color}")
                return lbl
        except Exception as e:
            logger.error(f"Error creating label '{name}' color '{color}': {e}")
            return None

    async def add_label_to_card(self, card_id: str, label_id: str):
        """Add an existing label to a card (no-op if already present)."""
        try:
            # POST /cards/{id}/idLabels with value=labelId
            url = f"{self.base_url}/cards/{card_id}/idLabels"
            params = {"key": self.api_key, "token": self.token, "value": label_id}
            async with httpx.AsyncClient() as client:
                r = await client.post(url, params=params)
                # Trello returns 400 if label already attached; handle gracefully
                if r.status_code in (200, 201):
                    return True
                else:
                    # if 400/409, treat as already present
                    return r.status_code < 400
        except Exception as e:
            logger.error(f"Error adding label {label_id} to card {card_id}: {e}")
            return False

    async def apply_label_to_list(self, list_id: str, label_name: str, color: str):
        """Ensure label exists and apply it to all cards in the given list id. Returns number of cards updated."""
        try:
            # ensure label exists
            lbl = await self.create_label_if_missing(label_name, color)
            if not lbl:
                return 0
            label_id = lbl.get('id')

            # fetch cards in list
            url = f"{self.base_url}/lists/{list_id}/cards"
            params = {"key": self.api_key, "token": self.token}
            async with httpx.AsyncClient() as client:
                r = await client.get(url, params=params)
                r.raise_for_status()
                cards = r.json()

            applied = 0
            for c in cards:
                card_id = c.get('id')
                if not card_id:
                    continue
                ok = await self.add_label_to_card(card_id, label_id)
                if ok:
                    applied += 1
            return applied
        except Exception as e:
            logger.error(f"Error applying label to list {list_id}: {e}")
            return 0

    async def archive_card(self, card_id: str) -> bool:
        """Archive a Trello card (set closed=true)"""
        try:
            url = f"{self.base_url}/cards/{card_id}"
            params = {
                "key": self.api_key,
                "token": self.token,
                "closed": "true",
            }
            async with httpx.AsyncClient() as client:
                response = await client.put(url, params=params)
                response.raise_for_status()
                logger.info(f"Card {card_id} archived")
                return True
        except Exception as e:
            logger.error(f"Error archiving Trello card {card_id}: {e}")
            return False

trello_service = TrelloService()

# ==================== EMAIL SERVICE ====================

class EmailService:
    def __init__(self):
        self.smtp_host = SMTP_HOST
        self.smtp_port = SMTP_PORT
        self.smtp_user = SMTP_USER
        self.smtp_password = SMTP_PASSWORD
        self.from_email = SMTP_FROM_EMAIL
        self.from_name = SMTP_FROM_NAME
    
    def send_email_sync(self, to_email: str, subject: str, body: str):
        """Send email synchronously (called from thread pool)"""
        try:
            # Validate SMTP configuration
            if not self.smtp_host or not self.smtp_user or not self.smtp_password:
                logger.error("SMTP configuration incomplete - skipping email send")
                return False
            msg = MIMEMultipart('alternative')
            msg['From'] = f"{self.from_name} <{self.from_email}>"
            msg['To'] = to_email
            msg['Subject'] = subject
            
            # HTML body
            html_part = MIMEText(body, 'html')
            msg.attach(html_part)
            
            # Connect and send
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
            
            logger.info(f"Email sent to {to_email}: {subject}")
            return True
        except Exception as e:
            logger.error(f"Error sending email to {to_email}: {e}")
            return False
    
    async def send_email(self, to_email: str, subject: str, body: str):
        """Send email asynchronously"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            email_executor,
            self.send_email_sync,
            to_email,
            subject,
            body
        )
    
    async def notify_rh_new_request(self, exam: dict, rh_users: List[dict]):
        """Notify RH users about new exam request"""
        subject = f"Nova Solicitação de Exame - {exam['nome']}"
        
        body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f9f9f9; border-radius: 10px;">
                <h2 style="color: #4F46E5;">📋 Nova Solicitação de Exame Demissional</h2>
                
                <div style="background-color: white; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <p><strong>Matrícula:</strong> {exam['matricula']}</p>
                    <p><strong>Nome:</strong> {exam['nome']}</p>
                    <p><strong>Data de Desligamento:</strong> {exam['data_desligamento']}</p>
                    <p><strong>Status:</strong> <span style="background-color: #DBEAFE; color: #1E40AF; padding: 4px 12px; border-radius: 12px;">Aguardando Agendamento</span></p>
                </div>
                
                <p style="margin-top: 20px;">Por favor, acesse o sistema para agendar o exame.</p>
                
                <a href="https://trello-integra.preview.emergentagent.com" 
                   style="display: inline-block; background-color: #4F46E5; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; margin-top: 10px;">
                    Acessar Sistema
                </a>
            </div>
        </body>
        </html>
        """
        
        for rh_user in rh_users:
            await self.send_email(rh_user['email'], subject, body)
    
    async def notify_dp_exam_scheduled(self, exam: dict, dp_user: dict):
        """Notify DP user that exam was scheduled"""
        subject = f"Exame Agendado - {exam['nome']}"
        
        body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f9f9f9; border-radius: 10px;">
                <h2 style="color: #059669;">✅ Exame Agendado</h2>
                
                <div style="background-color: white; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <p><strong>Matrícula:</strong> {exam['matricula']}</p>
                    <p><strong>Nome:</strong> {exam['nome']}</p>
                    <p><strong>Data do Exame:</strong> {exam.get('data_agendamento', 'A definir')}</p>
                    <p><strong>Status:</strong> <span style="background-color: #FEF3C7; color: #92400E; padding: 4px 12px; border-radius: 12px;">Agendado</span></p>
                </div>
                
                {f'<p><strong>Observações:</strong> {exam.get("observacoes", "")}</p>' if exam.get('observacoes') else ''}
                
                <a href="https://trello-integra.preview.emergentagent.com" 
                   style="display: inline-block; background-color: #059669; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; margin-top: 10px;">
                    Ver Detalhes
                </a>
            </div>
        </body>
        </html>
        """
        
        await self.send_email(dp_user['email'], subject, body)

    async def notify_dp_status_change(self, old_status: Optional[str], new_status: str, exam: dict, dp_user: dict):
        """Notify DP user on any status change"""
        subject, body = self.make_status_change_email(old_status, new_status, exam)
        await self.send_email(dp_user['email'], subject, body)

    def make_status_change_email(self, old_status: Optional[str], new_status: str, exam: dict):
        """Gera subject e body HTML para uma mudança de status (reutilizável em testes)."""
        status_labels = {
            'CRIADO': 'Criado',
            'EM_AGENDAMENTO': 'Agendado',
            'AGUARDANDO_RESULTADO': 'Aguardando Resultado',
            'APTO': 'Apto',
            'INAPTO': 'Inapto',
            'FINALIZADO': 'Finalizado',
        }
        old_key = old_status or ''
        new_key = new_status or ''
        old_label = status_labels.get(old_key, old_status or '-')
        new_label = status_labels.get(new_key, new_status or '-')

        color_map = {
            'CRIADO': ('#1E40AF', '#DBEAFE'),
            'EM_AGENDAMENTO': ('#92400E', '#FEF3C7'),
            'AGUARDANDO_RESULTADO': ('#9A3412', '#FFEDD5'),
            'APTO': ('#059669', '#D1FAE5'),
            'INAPTO': ('#DC2626', '#FEE2E2'),
            'FINALIZADO': ('#374151', '#E5E7EB'),
        }
        color, bg = color_map.get(new_status, ('#374151', '#E5E7EB'))

        subject = f"Status atualizado: {exam.get('nome', '')} — {new_label}"
        body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f9f9f9; border-radius: 10px;">
                <h2 style="color: #4F46E5;">🔔 Atualização de Status do Exame</h2>
                <div style="background-color: white; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <p><strong>Matrícula:</strong> {exam.get('matricula')}</p>
                    <p><strong>Nome:</strong> {exam.get('nome')}</p>
                    <p><strong>Data de Desligamento:</strong> {exam.get('data_desligamento', '-')}</p>
                    <p style="margin-top: 16px;"><strong>Status:</strong>
                        <span style="background-color: {bg}; color: {color}; padding: 6px 12px; border-radius: 12px; font-weight: 600;">
                            {new_label}
                        </span>
                    </p>
                    <p style="color:#6B7280; margin-top:8px;">Anterior: {old_label}</p>
                    {f"<p><strong>Data de Agendamento:</strong> {exam.get('data_agendamento')}</p>" if exam.get('data_agendamento') else ''}
                    {f"<p><strong>Observações:</strong> {exam.get('observacoes')}</p>" if exam.get('observacoes') else ''}
                </div>
                <a href="https://trello-integra.preview.emergentagent.com" 
                   style="display: inline-block; background-color: #4F46E5; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px;">
                    Abrir Sistema
                </a>
            </div>
        </body>
        </html>
        """
        return subject, body
    
    async def notify_dp_exam_result(self, exam: dict, dp_user: dict):
        """Notify DP user about exam result"""
        is_apto = exam['status'] == 'APTO'
        result_text = 'APTO' if is_apto else 'INAPTO'
        result_color = '#059669' if is_apto else '#DC2626'
        result_bg = '#D1FAE5' if is_apto else '#FEE2E2'
        
        subject = f"Resultado do Exame - {exam['nome']} - {result_text}"
        
        body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f9f9f9; border-radius: 10px;">
                <h2 style="color: {result_color};">📊 Resultado do Exame Demissional</h2>
                
                <div style="background-color: white; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <p><strong>Matrícula:</strong> {exam['matricula']}</p>
                    <p><strong>Nome:</strong> {exam['nome']}</p>
                    <p><strong>Data do Exame:</strong> {exam.get('data_agendamento', 'Não informada')}</p>
                    <p style="margin-top: 20px;">
                        <strong>Resultado:</strong> 
                        <span style="background-color: {result_bg}; color: {result_color}; padding: 8px 16px; border-radius: 12px; font-size: 18px; font-weight: bold;">
                            {result_text}
                        </span>
                    </p>
                </div>
                
                {f'<p><strong>Observações:</strong> {exam.get("observacoes", "")}</p>' if exam.get('observacoes') else ''}
                
                <p style="margin-top: 20px;">Acesse o sistema para mais detalhes e finalize o processo.</p>
                
                <a href="https://trello-integra.preview.emergentagent.com" 
                   style="display: inline-block; background-color: {result_color}; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; margin-top: 10px;">
                    Acessar Sistema
                </a>
            </div>
        </body>
        </html>
        """
        
        await self.send_email(dp_user['email'], subject, body)

email_service = EmailService()

# ==================== AUTH DEPENDENCIES ====================

async def get_current_user(
    authorization: Optional[str] = Cookie(None, alias="session_token"),
    auth_header: Optional[str] = Header(None, alias="Authorization")
) -> User:
    """Get current authenticated user from session token"""
    session_token = authorization
    
    # Fallback to Authorization header if cookie not present
    if not session_token and auth_header:
        if auth_header.startswith("Bearer "):
            session_token = auth_header.replace("Bearer ", "")
    
    if not session_token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    # Find session in database
    session = await db.user_sessions.find_one({"session_token": session_token})
    if not session:
        raise HTTPException(status_code=401, detail="Invalid session")
    
    # Check if session expired
    expires_at = session['expires_at']
    if isinstance(expires_at, str):
        expires_at = datetime.fromisoformat(expires_at)
    if not expires_at.tzinfo:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    
    if expires_at < datetime.now(timezone.utc):
        await db.user_sessions.delete_one({"session_token": session_token})
        raise HTTPException(status_code=401, detail="Session expired")
    
    # Get user
    user = await db.users.find_one({"id": session['user_id']}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    # Apply impersonation department if present in session
    effective_user = User(**user)
    imp_dept = session.get("impersonate_department")
    if imp_dept in ["DP", "RH"]:
        effective_user.department = imp_dept
    return effective_user

def require_department(required_dept: str):
    """Dependency to require specific department"""
    async def department_checker(current_user: User = Depends(get_current_user)):
        if current_user.department != required_dept:
            raise HTTPException(
                status_code=403,
                detail=f"Access denied. This action requires {required_dept} department"
            )
        return current_user
    return department_checker

async def require_admin(current_user: User = Depends(get_current_user)):
    """Dependency to require admin access"""
    # Allow access if the user's stored department is ADMIN
    # or if their email is configured in ADMIN_EMAILS (admin list from env)
    try:
        user_email = (current_user.email or "").lower()
    except Exception:
        user_email = ""

    if current_user.department != "ADMIN" and user_email not in ADMIN_EMAILS:
        raise HTTPException(
            status_code=403,
            detail="Access denied. Admin privileges required"
        )
    return current_user

# ==================== AUTH ROUTES ====================

@api_router.post("/auth/session")
async def create_session(request: Request, response: Response):
    """Process Emergent Auth session_id and create user session"""
    try:
        session_id = request.headers.get("X-Session-ID")
        if not session_id:
            raise HTTPException(status_code=400, detail="X-Session-ID header required")
        
        # Call Emergent Auth API (async)
        async with httpx.AsyncClient() as client:
            auth_response = await client.get(
                "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data",
                headers={"X-Session-ID": session_id}
            )
            auth_response.raise_for_status()
            auth_data = auth_response.json()
        
        # Check if user exists
        existing_user = await db.users.find_one({"email": auth_data['email']}, {"_id": 0})
        
        if existing_user:
            user = User(**existing_user)
        else:
            # Create new user
            user = User(
                id=auth_data['id'],
                email=auth_data['email'],
                name=auth_data['name'],
                picture=auth_data.get('picture')
            )
            await db.users.insert_one(user.model_dump())
        
        # Create session
        session_token = auth_data['session_token']
        expires_at = datetime.now(timezone.utc) + timedelta(days=7)
        
        session = UserSession(
            user_id=user.id,
            session_token=session_token,
            expires_at=expires_at
        )
        
        # Save session with proper datetime serialization
        session_dict = session.model_dump()
        await db.user_sessions.insert_one(session_dict)
        
        # Set httpOnly cookie
        # In dev (COOKIE_SECURE=false), use SameSite=Lax to allow cookies over HTTP
        secure = COOKIE_SECURE
        samesite = "none" if secure else "lax"
        response.set_cookie(
            key="session_token",
            value=session_token,
            httponly=True,
            secure=secure,
            samesite=samesite,
            path="/",
            max_age=7*24*60*60
        )
        
        return {
            "user": user.model_dump(),
            "session_token": session_token
        }
    
    except requests.RequestException as e:
        logger.error(f"Auth API error: {e}")
        raise HTTPException(status_code=500, detail="Authentication failed")
    except Exception as e:
        logger.error(f"Session creation error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@api_router.post("/auth/dev-login")
async def dev_login(payload: DevLoginRequest, response: Response):
    """DEV ONLY: cria sessão local sem provedor externo.
    Habilite com env DEV_AUTH_ENABLED=true.
    Permite definir `department`; se for "ADMIN" exige estar em ADMIN_EMAILS.
    """
    if os.environ.get("DEV_AUTH_ENABLED", "false").lower() != "true":
        raise HTTPException(status_code=404, detail="Not Found")

    try:
        # upsert user
        existing = await db.users.find_one({"email": payload.email.lower()}, {"_id": 0})
        if existing:
            # optionally update name/department
            update_set = {}
            if payload.name and payload.name != existing.get("name"):
                update_set["name"] = payload.name
            if payload.department:
                if payload.department == "ADMIN" and payload.email.lower() not in ADMIN_EMAILS:
                    raise HTTPException(status_code=403, detail="You are not authorized to be an administrator")
                update_set["department"] = payload.department
            if update_set:
                await db.users.update_one({"email": payload.email.lower()}, {"$set": update_set})
            user = await db.users.find_one({"email": payload.email.lower()}, {"_id": 0})
        else:
            dept = payload.department
            if dept == "ADMIN" and payload.email.lower() not in ADMIN_EMAILS:
                raise HTTPException(status_code=403, detail="You are not authorized to be an administrator")
            user = User(
                email=payload.email.lower(),
                name=payload.name,
                department=dept
            ).model_dump()
            await db.users.insert_one(user)

        # create session
        session_token = str(uuid.uuid4())
        expires_at = datetime.now(timezone.utc) + timedelta(days=7)
        # ensure we have a user id (user may be dict from DB or model_dump())
        user_id = None
        if isinstance(user, dict):
            user_id = user.get("id")
        else:
            user_id = getattr(user, "id", None)
        if not user_id:
            logger.error("dev_login: cannot determine user id for session creation")
            raise HTTPException(status_code=500, detail="Failed to create session (user id missing)")

        session = UserSession(
            user_id=user_id,
            session_token=session_token,
            expires_at=expires_at
        ).model_dump()
        await db.user_sessions.insert_one(session)

        # set cookie
        secure = COOKIE_SECURE
        samesite = "none" if secure else "lax"
        response.set_cookie(
            key="session_token",
            value=session_token,
            httponly=True,
            secure=secure,
            samesite=samesite,
            path="/",
            max_age=7*24*60*60
        )

        return {"user": user, "session_token": session_token}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Dev login error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@api_router.get("/auth/me")
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current user information"""
    return current_user

@api_router.get("/auth/can-be-admin")
async def can_be_admin(current_user: User = Depends(get_current_user)):
    """Check if current user can be admin"""
    is_authorized = current_user.email.lower() in ADMIN_EMAILS
    return {"can_be_admin": is_authorized}

@api_router.get("/auth/admin-emails")
async def list_admin_emails(admin_user: User = Depends(require_admin)):
    """List emails configured as administrators (ADMIN_EMAILS). Admin-only."""
    return {"admin_emails": ADMIN_EMAILS}

@api_router.get("/auth/impersonation-status")
async def impersonation_status(
    authorization: Optional[str] = Cookie(None, alias="session_token"),
    auth_header: Optional[str] = Header(None, alias="Authorization"),
    current_user: User = Depends(get_current_user)
):
    """Return whether current session is impersonating a sector and which one."""
    session_token = authorization
    if not session_token and auth_header and auth_header.startswith("Bearer "):
        session_token = auth_header.replace("Bearer ", "")
    if not session_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    session = await db.user_sessions.find_one({"session_token": session_token}, {"_id": 0})
    imp = session.get("impersonate_department") if session else None
    return {
        "is_impersonating": imp in ["DP", "RH"],
        "impersonate_department": imp if imp in ["DP", "RH"] else None,
        "effective_department": current_user.department,
    }

@api_router.post("/auth/department")
async def set_department(
    dept: DepartmentSelection,
    current_user: User = Depends(get_current_user)
):
    """Set user's department (DP or RH or ADMIN)"""
    if dept.department not in ["DP", "RH", "ADMIN"]:
        raise HTTPException(status_code=400, detail="Department must be 'DP', 'RH', or 'ADMIN'")
    
    # Check if user is authorized to be ADMIN
    if dept.department == "ADMIN":
        if current_user.email.lower() not in ADMIN_EMAILS:
            raise HTTPException(
                status_code=403,
                detail="You are not authorized to be an administrator"
            )
    
    await db.users.update_one(
        {"id": current_user.id},
        {"$set": {"department": dept.department}}
    )
    
    logger.info(f"User {current_user.email} set department to {dept.department}")
    
    return {"message": "Department updated", "department": dept.department}

@api_router.post("/auth/impersonate-department")
async def impersonate_department(
    dept: DepartmentSelection,
    response: Response,
    admin_user: User = Depends(require_admin),
    authorization: Optional[str] = Cookie(None, alias="session_token"),
    auth_header: Optional[str] = Header(None, alias="Authorization")
):
    """ADMIN only: start acting as a sector (DP/RH) in this session without changing stored user department."""
    if dept.department not in ["DP", "RH"]:
        raise HTTPException(status_code=400, detail="Department must be 'DP' or 'RH'")

    # Determine session token
    session_token = authorization
    if not session_token and auth_header and auth_header.startswith("Bearer "):
        session_token = auth_header.replace("Bearer ", "")
    if not session_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    # Update current session with impersonation flag
    await db.user_sessions.update_one(
        {"session_token": session_token},
        {"$set": {"impersonate_department": dept.department}}
    )

    logger.info(f"Admin {admin_user.email} is impersonating department {dept.department}")

    return {"message": "Impersonation started", "impersonate_department": dept.department}

@api_router.post("/auth/stop-impersonation")
async def stop_impersonation(
    response: Response,
    authorization: Optional[str] = Cookie(None, alias="session_token"),
    auth_header: Optional[str] = Header(None, alias="Authorization"),
    current_user: User = Depends(get_current_user)
):
    """Stop acting as a sector in this session. Works even while impersonating."""
    # Determine session token
    session_token = authorization
    if not session_token and auth_header and auth_header.startswith("Bearer "):
        session_token = auth_header.replace("Bearer ", "")
    if not session_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    await db.user_sessions.update_one(
        {"session_token": session_token},
        {"$unset": {"impersonate_department": ""}}
    )

    logger.info("Stopped impersonation for current session")
    return {"message": "Impersonation stopped"}

@api_router.post("/auth/logout")
async def logout(
    response: Response,
    session_token: Optional[str] = Cookie(None)
):
    """Logout user and delete session"""
    if session_token:
        await db.user_sessions.delete_one({"session_token": session_token})
    
    response.delete_cookie(key="session_token", path="/")
    return {"message": "Logged out successfully"}

# ==================== ADMIN ROUTES ====================

@api_router.get("/admin/users", response_model=List[User])
async def list_all_users(admin_user: User = Depends(require_admin)):
    """List all users (Admin only)"""
    try:
        users = await db.users.find({}, {"_id": 0}).to_list(1000)
        return users
    except Exception as e:
        logger.error(f"Error listing users: {e}")
        raise HTTPException(status_code=500, detail="Failed to list users")

@api_router.patch("/admin/users/{user_id}")
async def update_user_department(
    user_id: str,
    update: UserUpdate,
    admin_user: User = Depends(require_admin)
):
    """Update user department (Admin only)"""
    try:
        if update.department not in ["DP", "RH", "ADMIN"]:
            raise HTTPException(
                status_code=400,
                detail="Department must be 'DP', 'RH', or 'ADMIN'"
            )
        
        # Check if user exists
        user = await db.users.find_one({"id": user_id}, {"_id": 0})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Update department
        await db.users.update_one(
            {"id": user_id},
            {"$set": {"department": update.department}}
        )
        
        logger.info(f"Admin {admin_user.email} changed user {user['email']} department to {update.department}")
        
        return {
            "message": "User department updated successfully",
            "user_id": user_id,
            "new_department": update.department
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating user department: {e}")
        raise HTTPException(status_code=500, detail="Failed to update user department")

@api_router.delete("/admin/users/{user_id}")
async def delete_user(
    user_id: str,
    admin_user: User = Depends(require_admin)
):
    """Delete a user and their sessions (Admin only). Prevent self-deletion."""
    try:
        # Check if user exists
        user = await db.users.find_one({"id": user_id}, {"_id": 0})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Prevent admin from deleting themselves
        if user_id == admin_user.id:
            raise HTTPException(status_code=400, detail="You cannot delete your own user")

        # Delete user sessions
        await db.user_sessions.delete_many({"user_id": user_id})
        # Delete user document
        await db.users.delete_one({"id": user_id})

        logger.info(f"Admin {admin_user.email} deleted user {user.get('email')}")
        return {"message": "User deleted successfully", "user_id": user_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting user: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete user")

@api_router.post("/admin/purge-exams")
async def admin_purge_exams(admin_user: User = Depends(require_admin)):
    """Delete ALL exam requests from the database. Admin only."""
    try:
        result = await db.exam_requests.delete_many({})
        logger.info(f"Admin {admin_user.email} purged exam_requests. Deleted: {result.deleted_count}")
        return {"deleted": result.deleted_count}
    except Exception as e:
        logger.error(f"Error purging exam requests: {e}")
        raise HTTPException(status_code=500, detail="Failed to purge exam requests")


class TestNotificationRequest(BaseModel):
    exam_id: Optional[str] = None
    dry_run: bool = True
    override_recipient: Optional[str] = None  # if provided, send only to this email


@api_router.post("/admin/test-notifications")
async def admin_test_notifications(
    payload: TestNotificationRequest,
    admin_user: User = Depends(require_admin)
):
    """Endpoint admin: testa envio de notificações para todos os status.

    - Se `exam_id` fornecido, usa esse exame; caso contrário cria um exame fake (em memória).
    - `dry_run` por padrão true; se false enviará emails reais para destinatários encontrados.
    - `override_recipient` envia apenas para o email especificado (útil para testes).
    """
    try:
        statuses = ["CRIADO", "EM_AGENDAMENTO", "AGUARDANDO_RESULTADO", "APTO", "INAPTO"]

        # Fetch exam or build fake
        if payload.exam_id:
            exam = await db.exam_requests.find_one({"id": payload.exam_id}, {"_id": 0})
            if not exam:
                raise HTTPException(status_code=404, detail="Exam not found")
        else:
            # Fake exam for preview
            exam = {
                "id": "test-exam-000",
                "matricula": "000000",
                "nome": "Usuário Teste",
                "data_desligamento": datetime.now(timezone.utc).date().isoformat(),
                "status": "CRIADO",
                "data_agendamento": None,
                "observacoes": "Teste de notificação",
            }

        results = []
        for st in statuses:
            # Build recipients according to same rules used in update endpoint
            recipients = []
            if st in ["EM_AGENDAMENTO", "AGUARDANDO_RESULTADO"]:
                recipients += await db.users.find({"department": "DP"}, {"_id": 0}).to_list(2000)
                recipients += await db.users.find({"department": "RH"}, {"_id": 0}).to_list(2000)
            elif st in ["APTO", "INAPTO"]:
                recipients += await db.users.find({"department": "DP"}, {"_id": 0}).to_list(2000)
                recipients += await db.users.find({"department": "RH"}, {"_id": 0}).to_list(2000)
                recipients += await db.users.find({"department": "ADMIN"}, {"_id": 0}).to_list(2000)
            else:
                recipients += await db.users.find({"department": "DP"}, {"_id": 0}).to_list(2000)
                recipients += await db.users.find({"department": "RH"}, {"_id": 0}).to_list(2000)

            # Apply override_recipient if provided
            if payload.override_recipient:
                recipients = [{"email": payload.override_recipient, "name": "Override Recipient"}]

            # Deduplicate
            seen = set()
            unique = []
            for u in recipients:
                email = (u.get("email") or "").lower()
                if email and email not in seen:
                    seen.add(email)
                    unique.append(u)

            sent = 0
            previews = []
            for user_rec in unique:
                try:
                    subject, body = email_service.make_status_change_email(None, st, exam)
                    previews.append({"to": user_rec.get("email"), "subject": subject})
                    if not payload.dry_run:
                        await email_service.send_email(user_rec.get("email"), subject, body)
                        sent += 1
                except Exception as e:
                    logger.error(f"Test notify failed for {user_rec.get('email')}: {e}")

            results.append({"status": st, "recipients_count": len(unique), "sent": sent, "previews": previews[:10]})

        return {"ok": True, "dry_run": payload.dry_run, "results": results}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"admin_test_notifications error: {e}")
        raise HTTPException(status_code=500, detail="Failed to run test notifications")

# ==================== EXAM ROUTES ====================

@api_router.post("/exams", response_model=ExamRequest)
async def create_exam_request(
    exam: ExamRequestCreate,
    current_user: User = Depends(require_department("DP"))
):
    """Create new exam request (DP only)"""
    try:
        # Validação: matrícula deve conter exatamente 8 dígitos numéricos
        matricula_raw = (exam.matricula or "").strip()
        if not re.fullmatch(r"\d{8}", matricula_raw):
            raise HTTPException(status_code=400, detail="Matrícula deve conter exatamente 8 dígitos numéricos")
        # Normalize matricula e nome no payload
        exam_payload = exam.model_dump()
        exam_payload['matricula'] = matricula_raw
        # Forçar nome em maiúsculas
        exam_payload['nome'] = (exam_payload.get('nome') or '').upper()
        # Validação: data_desligamento deve ser hoje ou data futura (compara apenas a parte de data)
        try:
            ds = exam_payload.get('data_desligamento')
            if not ds:
                raise HTTPException(status_code=400, detail="Data de desligamento é obrigatória")
            # assume formato YYYY-MM-DD
            ds_date = datetime.fromisoformat(ds).date()
            today_date = datetime.now(timezone.utc).date()
            if ds_date < today_date:
                raise HTTPException(status_code=400, detail="Data de desligamento deve ser hoje ou uma data futura")
        except ValueError:
            raise HTTPException(status_code=400, detail="Data de desligamento com formato inválido (esperado YYYY-MM-DD)")
        # Create exam request
        exam_request = ExamRequest(
            **exam_payload,
            created_by=current_user.id
        )

        # Create Trello card
        card_name = f"Exame - {exam.nome}"
        card_desc = f"Matrícula: {exam.matricula}\nNome: {exam.nome}\nData Desligamento: {exam.data_desligamento}\nStatus: CRIADO"

        card = await trello_service.create_card(card_name, card_desc, "Novas Solicitações DP")

        if card:
            exam_request.trello_card_id = card['id']
            exam_request.trello_card_url = card['url']

        # Save to database
        await db.exam_requests.insert_one(exam_request.model_dump())
        # Log history (created)
        try:
            await db.exam_history.insert_one({
                "id": str(uuid.uuid4()),
                "exam_id": exam_request.id,
                "event": "CREATED",
                "timestamp": datetime.now(timezone.utc),
                "actor_id": current_user.id,
                "actor_email": current_user.email,
                "actor_department": current_user.department,
                "payload": {
                    "matricula": exam_request.matricula,
                    "nome": exam_request.nome,
                    "data_desligamento": exam_request.data_desligamento,
                    "status": exam_request.status,
                },
            })
        except Exception as e:
            logger.error(f"Failed to log exam creation history: {e}")

        # 📧 Notificações ao criar (status CRIADO): DP e RH
        try:
            # Notificar apenas o criador do exame (current_user)
            creator = current_user.model_dump()
            try:
                await email_service.notify_dp_status_change(None, "CRIADO", exam_request.model_dump(), creator)
                logger.info(f"Email notification (CRIADO) sent to creator: {creator.get('email')}")
            except Exception as e:
                logger.error(f"Failed to notify creator {creator.get('email')}: {e}")
            # Notificar usuários do RH sobre nova solicitação
            try:
                rh_users = await db.users.find({"department": "RH"}, {"_id": 0}).to_list(2000)
                if rh_users:
                    await email_service.notify_rh_new_request(exam_request.model_dump(), rh_users)
                    logger.info(f"Email notification (CRIADO) sent to RH: {len(rh_users)} users")
            except Exception as rh_err:
                logger.error(f"Failed to notify RH users: {rh_err}")
        except Exception as email_error:
            logger.error(f"Error sending email notifications: {email_error}")
            # Do not fail request on email errors

        return exam_request
    except Exception as e:
        logger.error(f"Error creating exam request: {e}")
        raise HTTPException(status_code=500, detail="Failed to create exam request")

# ==================== TRELLO READ ENDPOINTS ====================

@api_router.get("/trello/lists")
async def trello_get_lists(current_user: User = Depends(get_current_user)):
    """Return Trello lists for the configured board."""
    _require_trello_env()
    api_key = os.environ.get('TRELLO_API_KEY')
    token = os.environ.get('TRELLO_TOKEN')
    board_id = os.environ.get('TRELLO_BOARD_ID')
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{TRELLO_BASE_URL}/boards/{board_id}/lists",
                params={"key": api_key, "token": token}
            )
            r.raise_for_status()
            lists = r.json()
            return [{
                "id": l.get("id"),
                "name": l.get("name"),
            } for l in lists]
    except httpx.HTTPError as e:
        logger.error(f"Trello lists error: {e}")
        raise HTTPException(status_code=502, detail="Failed to fetch Trello lists")

@api_router.get("/trello/board-snapshot")
async def trello_board_snapshot(current_user: User = Depends(get_current_user)):
    """Return all lists and their cards for the configured board in a single response.
    Response format:
    [
      { id, name, cards: [ {id, name, url, desc, due, labels, shortLink}, ... ] },
      ...
    ]
    """
    _require_trello_env()
    api_key = os.environ.get('TRELLO_API_KEY')
    token = os.environ.get('TRELLO_TOKEN')
    board_id = os.environ.get('TRELLO_BOARD_ID')
    try:
        async with httpx.AsyncClient() as client:
            # Fetch lists
            lr = await client.get(
                f"{TRELLO_BASE_URL}/boards/{board_id}/lists",
                params={"key": api_key, "token": token}
            )
            lr.raise_for_status()
            lists = lr.json()

            # Helper to fetch and map cards for a list
            async def fetch_cards(list_id: str):
                cr = await client.get(
                    f"{TRELLO_BASE_URL}/lists/{list_id}/cards",
                    params={"key": api_key, "token": token}
                )
                cr.raise_for_status()
                cards = cr.json()
                return [{
                    "id": c.get("id"),
                    "name": c.get("name"),
                    "url": c.get("url"),
                    "desc": c.get("desc"),
                    "due": c.get("due"),
                    "labels": c.get("labels", []),
                    "shortLink": c.get("shortLink"),
                } for c in cards]

            # Fetch cards in parallel
            tasks = [fetch_cards(lst.get("id")) for lst in lists]
            cards_per_list = await asyncio.gather(*tasks, return_exceptions=True)

            # Build response, handling any per-list error as empty list
            snapshot = []
            for idx, lst in enumerate(lists):
                cards = cards_per_list[idx]
                if isinstance(cards, Exception):
                    logger.error(f"Trello cards error for list {lst.get('id')}: {cards}")
                    cards = []
                snapshot.append({
                    "id": lst.get("id"),
                    "name": lst.get("name"),
                    "cards": cards
                })
            return snapshot
    except httpx.HTTPError as e:
        logger.error(f"Trello board snapshot error: {e}")
        raise HTTPException(status_code=502, detail="Failed to fetch Trello board snapshot")

# ==================== TRELLO <-> DASHBOARD SYNC ====================

# Centralize mapping between statuses and Trello list names
STATUS_TO_LIST = {
    "EM_AGENDAMENTO": "Agendado",
    "AGUARDANDO_RESULTADO": "Aguardando Resultado",
    "APTO": "Apto",
    "INAPTO": "Inapto",
}

LIST_TO_STATUS = {v: k for k, v in STATUS_TO_LIST.items()}

def _parse_card_desc(desc: str) -> dict:
    """Parse Trello card description generated by this app into fields.
    Expected lines (Portuguese):
      Matrícula: 123
      Nome: Fulano
      Data Desligamento: 2025-01-10
      Status: CRIADO|EM_AGENDAMENTO|AGUARDANDO_RESULTADO|APTO|INAPTO
      Data Agendamento: 2025-01-15 (opcional)
      Observações: ... (opcional)
    """
    if not desc:
        return {}
    result = {}
    try:
        for raw_line in desc.splitlines():
            line = raw_line.strip()
            if not line or ":" not in line:
                continue
            key, value = line.split(":", 1)
            key = key.strip().lower()
            value = value.strip()
            if key == "matrícula" or key == "matricula":
                result["matricula"] = value
            elif key == "nome":
                result["nome"] = value
            elif key == "data desligamento" or key == "data_desligamento":
                result["data_desligamento"] = value
            elif key == "status":
                result["status"] = value
            elif key == "data agendamento" or key == "data_agendamento":
                result["data_agendamento"] = value
            elif key == "observações" or key == "observacoes":
                result["observacoes"] = value
    except Exception as e:
        logger.warning(f"Failed parsing Trello desc: {e}")
    return result

@api_router.head("/trello/webhook")
async def trello_webhook_verify():
    """Trello calls HEAD on the callback URL to verify reachability."""
    return Response(status_code=200)

@api_router.post("/trello/webhook")
async def trello_webhook(request: Request):
    """Receive Trello webhook events and update local DB accordingly.

    This handler updates `exam_requests` when the associated Trello card is moved
    across lists (status change) or when description is edited (fields sync).
    """
    try:
        payload = await request.json()
        action = payload.get("action", {})
        card = action.get("data", {}).get("card", {})
        card_id = card.get("id")
        if not card_id:
            return {"ignored": True}

        # Locate exam by trello_card_id
        exam = await db.exam_requests.find_one({"trello_card_id": card_id}, {"_id": 0})
        if not exam:
            # Not created by our system or not linked
            return {"ignored": True}

        update_fields = {}
        action_type = action.get("type")

        # Card moved to another list -> status update
        if action_type == "updateCard":
            data = action.get("data", {})
            if "listAfter" in data and data.get("listAfter", {}).get("name"):
                list_name = data["listAfter"]["name"]
                status = LIST_TO_STATUS.get(list_name)
                if status:
                    update_fields["status"] = status

            # Description change -> parse fields
            if "old" in data and "desc" in data["old"]:
                new_desc = data.get("card", {}).get("desc") or ""
                parsed = _parse_card_desc(new_desc)
                # only carry whitelisted keys
                for key in ("data_agendamento", "observacoes"):
                    if key in parsed:
                        update_fields[key] = parsed[key]

        # If we have something to update, persist and stamp updated_at
        if update_fields:
            update_fields["updated_at"] = datetime.now(timezone.utc)
            await db.exam_requests.update_one(
                {"trello_card_id": card_id},
                {"$set": update_fields}
            )
            logger.info("Synced Trello->DB for card %s: %s", card_id, update_fields)

        return {"ok": True}
    except Exception as e:
        logger.error(f"Trello webhook error: {e}")
        return JSONResponse(status_code=200, content={"ok": False})

@api_router.post("/trello/sync-now")
async def trello_sync_now(current_user: User = Depends(require_admin)):
    """Manually poll Trello lists/cards and reconcile local DB by `trello_card_id`.
    Admin-only to avoid accidental overload.
    """
    _require_trello_env()
    updated = 0
    try:
        lists = await trello_service.get_lists()
        if not lists:
            return {"updated": 0}
        async with httpx.AsyncClient() as client:
            for list_name, list_id in lists.items():
                r = await client.get(
                    f"{TRELLO_BASE_URL}/lists/{list_id}/cards",
                    params={"key": TRELLO_API_KEY, "token": TRELLO_TOKEN}
                )
                r.raise_for_status()
                for c in r.json():
                    card_id = c.get("id")
                    if not card_id:
                        continue
                    exam = await db.exam_requests.find_one({"trello_card_id": card_id}, {"_id": 0})
                    if not exam:
                        continue

                    update_fields = {}
                    # list -> status
                    status = LIST_TO_STATUS.get(list_name)
                    if status and status != exam.get("status"):
                        update_fields["status"] = status

                    # desc -> parse fields
                    parsed = _parse_card_desc(c.get("desc") or "")
                    for key in ("data_agendamento", "observacoes"):
                        if key in parsed and parsed[key] != exam.get(key):
                            update_fields[key] = parsed[key]

                    if update_fields:
                        update_fields["updated_at"] = datetime.now(timezone.utc)
                        await db.exam_requests.update_one(
                            {"trello_card_id": card_id},
                            {"$set": update_fields}
                        )
                        updated += 1
        return {"updated": updated}
    except Exception as e:
        logger.error(f"Manual Trello sync error: {e}")
        raise HTTPException(status_code=500, detail="Failed Trello sync")


@api_router.post("/trello/sync-list-colors")
async def trello_sync_list_colors(admin_user: User = Depends(require_admin)):
    """Admin: cria/aplica labels coloridos para listas no board conforme regras do dashboard."""
    try:
        _require_trello_env()
        lists = await trello_service.get_lists()
        if not lists:
            return {"updated": 0, "message": "No lists found"}

        # mapping name -> (labelName, color)
        def mapping(name: str):
            n = (name or '').lower()
            if 'nova' in n or 'solicita' in n:
                return ("Novas Solicitações", "blue")
            if 'agendado' in n:
                return ("Agendado", "yellow")
            if 'aguardando' in n:
                return ("Aguardando Resultado", "orange")
            if 'inapto' in n:
                return ("Inapto", "red")
            if 'apto' in n:
                return ("Apto", "green")
            return (None, None)

        updated = 0
        # lists is a dict name->id
        for name, list_id in lists.items():
            lbl_name, color = mapping(name)
            if not lbl_name or not color:
                continue
            applied = await trello_service.apply_label_to_list(list_id, lbl_name, color)
            updated += applied

        return {"ok": True, "applied_labels_to_cards": updated}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error syncing list colors: {e}")
        raise HTTPException(status_code=500, detail="Failed to sync list colors")

@api_router.get("/exams", response_model=List[ExamRequest])
async def get_exam_requests(
    include_finalized: Optional[bool] = Query(True, description="Include exams with status FINALIZADO"),
    current_user: User = Depends(get_current_user)
):
    """Get all exam requests"""
    try:
        # If include_finalized is False, filter out exams with status FINALIZADO at the DB level
        query = {}
        if include_finalized is False:
            query = {"status": {"$ne": "FINALIZADO"}}
        exams = await db.exam_requests.find(query, {"_id": 0}).to_list(1000)
        return exams
    
    except Exception as e:
        logger.error(f"Error fetching exam requests: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch exam requests")

@api_router.get("/exams/{exam_id}", response_model=ExamRequest)
async def get_exam_request(
    exam_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get specific exam request"""
    exam = await db.exam_requests.find_one({"id": exam_id}, {"_id": 0})
    if not exam:
        raise HTTPException(status_code=404, detail="Exam request not found")
    
    return exam

@api_router.patch("/exams/{exam_id}")
async def update_exam_request(
    exam_id: str,
    update: ExamRequestUpdate,
    current_user: User = Depends(get_current_user)
):
    """Update exam request"""
    try:
        # Get existing exam
        exam = await db.exam_requests.find_one({"id": exam_id}, {"_id": 0})
        if not exam:
            raise HTTPException(status_code=404, detail="Exam request not found")
        
        # Check permissions
        if current_user.department == "DP" and exam['created_by'] != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")

        # Only DP can set status to FINALIZADO
        if update.status == "FINALIZADO" and current_user.department != "DP":
            raise HTTPException(status_code=403, detail="Apenas DP pode definir status FINALIZADO")
        
        # Store old status to detect changes
        old_status = exam['status']
        
        # Prepare update
        update_data = {k: v for k, v in update.model_dump().items() if v is not None}
        update_data['updated_at'] = datetime.now(timezone.utc)
        
        # Update database
        await db.exam_requests.update_one(
            {"id": exam_id},
            {"$set": update_data}
        )
        
        # Get updated exam for notifications
        updated_exam = await db.exam_requests.find_one({"id": exam_id}, {"_id": 0})
        if not updated_exam:
            updated_exam = exam
        
        # Update Trello card if status changed
        if update.status and exam.get('trello_card_id'):
            # Se finalizado, arquivar o card
            if update.status == "FINALIZADO":
                await trello_service.archive_card(exam['trello_card_id'])
            else:
                status_to_list = {
                    "EM_AGENDAMENTO": "Agendado",
                    "AGUARDANDO_RESULTADO": "Aguardando Resultado",
                    "APTO": "Apto",
                    "INAPTO": "Inapto"
                }
                target_list = status_to_list.get(update.status)
                if target_list:
                    await trello_service.move_card(exam['trello_card_id'], target_list)
                
                # Update card description
                new_desc = f"Matrícula: {exam['matricula']}\nNome: {exam['nome']}\nData Desligamento: {exam['data_desligamento']}\nStatus: {update.status}"
                if update.data_agendamento:
                    new_desc += f"\nData Agendamento: {update.data_agendamento}"
                if update.observacoes:
                    new_desc += f"\nObservações: {update.observacoes}"
                await trello_service.update_card(exam['trello_card_id'], description=new_desc)
        
        # Log history changes
        try:
            history_payload = {k: v for k, v in update_data.items() if k != 'updated_at'}
            if history_payload:
                await db.exam_history.insert_one({
                    "id": str(uuid.uuid4()),
                    "exam_id": exam_id,
                    "event": "UPDATED",
                    "timestamp": datetime.now(timezone.utc),
                    "actor_id": current_user.id,
                    "actor_email": current_user.email,
                    "actor_department": current_user.department,
                    "old_status": old_status,
                    "new_status": update.status or old_status,
                    "payload": history_payload,
                })
        except Exception as e:
            logger.error(f"Failed to log exam update history: {e}")

        # 📧 Notificações por mudança de status conforme regra
        try:
            if update.status and update.status != old_status:
                # Construir lista de destinatários
                recipients = []
                # Sempre DP e RH para EM_AGENDAMENTO/AGUARDANDO_RESULTADO
                if update.status in ["EM_AGENDAMENTO", "AGUARDANDO_RESULTADO"]:
                    recipients += await db.users.find({"department": "DP"}, {"_id": 0}).to_list(2000)
                    recipients += await db.users.find({"department": "RH"}, {"_id": 0}).to_list(2000)
                # Para APTO/INAPTO -> DP, RH e ADMIN (FINALIZADO não notifica)
                elif update.status in ["APTO", "INAPTO"]:
                    recipients += await db.users.find({"department": "DP"}, {"_id": 0}).to_list(2000)
                    recipients += await db.users.find({"department": "RH"}, {"_id": 0}).to_list(2000)
                    recipients += await db.users.find({"department": "ADMIN"}, {"_id": 0}).to_list(2000)
                # Outros status (fallback): DP e RH
                else:
                    recipients += await db.users.find({"department": "DP"}, {"_id": 0}).to_list(2000)
                    recipients += await db.users.find({"department": "RH"}, {"_id": 0}).to_list(2000)

                # Deduplicar por email
                seen = set()
                unique_recipients = []
                for u in recipients:
                    email = (u.get("email") or "").lower()
                    if email and email not in seen:
                        seen.add(email)
                        unique_recipients.append(u)

                sent = 0
                for user_rec in unique_recipients:
                    try:
                        # Skip sending when new status is FINALIZADO
                        if update.status == "FINALIZADO":
                            continue
                        await email_service.notify_dp_status_change(old_status, update.status, updated_exam, user_rec)
                        sent += 1
                    except Exception as e:
                        logger.error(f"Failed to notify {user_rec.get('email')}: {e}")
                logger.info(f"Status change notifications sent: {sent} users for status {update.status}")

        except Exception as email_error:
            logger.error(f"Error sending email notification: {email_error}")
            # Don't fail the request if email fails
        
        return {"message": "Exam request updated successfully"}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating exam request: {e}")
        raise HTTPException(status_code=500, detail="Failed to update exam request")


@api_router.delete("/exams/{exam_id}")
async def delete_exam_request(
    exam_id: str,
    admin_user: User = Depends(require_admin)
):
    """Delete an exam request (Admin only).

    - Archives the Trello card if linked.
    - Inserts a history event of type DELETED.
    - Removes the exam document from the database.
    """
    try:
        exam = await db.exam_requests.find_one({"id": exam_id}, {"_id": 0})
        if not exam:
            raise HTTPException(status_code=404, detail="Exam request not found")

        # Archive Trello card when present (best-effort)
        trello_id = exam.get("trello_card_id")
        if trello_id:
            try:
                await trello_service.archive_card(trello_id)
            except Exception as e:
                logger.warning(f"Failed to archive Trello card {trello_id} for exam {exam_id}: {e}")

        # Log deletion in history
        try:
            await db.exam_history.insert_one({
                "id": str(uuid.uuid4()),
                "exam_id": exam_id,
                "event": "DELETED",
                "timestamp": datetime.now(timezone.utc),
                "actor_id": admin_user.id,
                "actor_email": admin_user.email,
                "actor_department": admin_user.department,
                "payload": {
                    "matricula": exam.get("matricula"),
                    "nome": exam.get("nome"),
                    "status": exam.get("status"),
                },
            })
        except Exception as e:
            logger.error(f"Failed to log exam deletion history for {exam_id}: {e}")

        # Delete exam document
        result = await db.exam_requests.delete_one({"id": exam_id})
        logger.info(f"Admin {admin_user.email} deleted exam {exam_id} (deleted_count={getattr(result, 'deleted_count', None)})")

        return {"message": "Exam request deleted successfully", "exam_id": exam_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting exam request: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete exam request")

# ==================== ADMIN HISTORY ROUTES ====================

@api_router.get("/admin/history")
async def list_history(
    exam_id: Optional[str] = None,
    actor_email: Optional[str] = None,
    limit: int = 200,
    admin_user: User = Depends(require_admin),
):
    """List exam history events (Admin only)"""
    try:
        q = {}
        if exam_id:
            q["exam_id"] = exam_id
        if actor_email:
            q["actor_email"] = actor_email
        limit = max(1, min(limit, 1000))
        # Most recent first
        cursor = db.exam_history.find(q, {"_id": 0}).sort("timestamp", -1).limit(limit)
        items = await cursor.to_list(limit)
        # Normalize timestamp ISO
        for it in items:
            ts = it.get("timestamp")
            if isinstance(ts, datetime):
                if not ts.tzinfo:
                    ts = ts.replace(tzinfo=timezone.utc)
                it["timestamp"] = ts.isoformat()
        return items
    except Exception as e:
        logger.error(f"Error listing history: {e}")
        raise HTTPException(status_code=500, detail="Failed to list history")

# ==================== HEALTH CHECK ====================

@api_router.get("/")
async def root():
    return {"message": "Exam Management System API"}

@api_router.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()


# Public health endpoint (no /api prefix) so load balancers / k8s can probe /health
@app.get("/health")
async def public_health_check():
    return {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat()}


# Readiness endpoint: checks env and Mongo connectivity. Returns 200 when ready, 503 otherwise.
@api_router.get("/health/ready")
async def readiness_check_api():
    return await _do_readiness_check()


@app.get("/health/ready")
async def readiness_check():
    return await _do_readiness_check()


async def _do_readiness_check():
    details = {}
    overall_ok = True

    # Required environment vars
    required_env = [
        'MONGO_URL',
        'DB_NAME',
    ]
    missing = [v for v in required_env if not os.environ.get(v)]
    if missing:
        details['env'] = {'ok': False, 'missing': missing}
        overall_ok = False
    else:
        details['env'] = {'ok': True}

    # Mongo ping
    try:
        # Motor's AsyncIOMotorClient exposes admin.command
        await client.admin.command({'ping': 1})
        details['mongo'] = {'ok': True}
    except Exception as e:
        details['mongo'] = {'ok': False, 'error': str(e)}
        overall_ok = False

    status = 200 if overall_ok else 503
    payload = {
        'status': 'ready' if overall_ok else 'unready',
        'details': details,
        'timestamp': datetime.now(timezone.utc).isoformat(),
    }
    return JSONResponse(status_code=status, content=payload)
