from fastapi import FastAPI, APIRouter, HTTPException, Depends, Response, Request, Cookie
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

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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
                    <p><strong>Status:</strong> <span style="background-color: #FEF3C7; color: #92400E; padding: 4px 12px; border-radius: 12px;">Em Agendamento</span></p>
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
    auth_header: Optional[str] = None
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
    
    return User(**user)

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
    if current_user.department != "ADMIN":
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
        
        # Call Emergent Auth API
        auth_response = requests.get(
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
        response.set_cookie(
            key="session_token",
            value=session_token,
            httponly=True,
            secure=True,
            samesite="none",
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

@api_router.get("/auth/me")
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current user information"""
    return current_user

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

# ==================== EXAM ROUTES ====================

@api_router.post("/exams", response_model=ExamRequest)
async def create_exam_request(
    exam: ExamRequestCreate,
    current_user: User = Depends(require_department("DP"))
):
    """Create new exam request (DP only)"""
    try:
        # Create exam request
        exam_request = ExamRequest(
            **exam.model_dump(),
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
        
        # 📧 Send email notification to RH users
        try:
            rh_users = await db.users.find({"department": "RH"}, {"_id": 0}).to_list(100)
            if rh_users:
                await email_service.notify_rh_new_request(exam_request.model_dump(), rh_users)
                logger.info(f"Email notifications sent to {len(rh_users)} RH users")
        except Exception as email_error:
            logger.error(f"Error sending email notifications: {email_error}")
            # Don't fail the request if email fails
        
        return exam_request
    
    except Exception as e:
        logger.error(f"Error creating exam request: {e}")
        raise HTTPException(status_code=500, detail="Failed to create exam request")
        await db.exam_requests.insert_one(exam_request.model_dump())
        
        return exam_request
    
    except Exception as e:
        logger.error(f"Error creating exam request: {e}")
        raise HTTPException(status_code=500, detail="Failed to create exam request")

@api_router.get("/exams", response_model=List[ExamRequest])
async def get_exam_requests(
    current_user: User = Depends(get_current_user)
):
    """Get all exam requests (filtered by department)"""
    try:
        query = {}
        
        # DP sees only their created requests
        if current_user.department == "DP":
            query["created_by"] = current_user.id
        
        # RH sees all requests
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
        
        # Update Trello card if status changed
        if update.status and exam.get('trello_card_id'):
            status_to_list = {
                "EM_AGENDAMENTO": "Em Agendamento (RH)",
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
        
        # 📧 Send email notifications based on status change
        try:
            if update.status and update.status != old_status:
                # Get DP user who created the request
                dp_user = await db.users.find_one({"id": exam['created_by']}, {"_id": 0})
                
                if dp_user:
                    # Notify DP when RH schedules exam
                    if update.status == "EM_AGENDAMENTO":
                        await email_service.notify_dp_exam_scheduled(updated_exam, dp_user)
                        logger.info(f"Exam scheduled notification sent to {dp_user['email']}")
                    
                    # Notify DP when result is available
                    elif update.status in ["APTO", "INAPTO"]:
                        await email_service.notify_dp_exam_result(updated_exam, dp_user)
                        logger.info(f"Exam result notification sent to {dp_user['email']}")
        
        except Exception as email_error:
            logger.error(f"Error sending email notification: {email_error}")
            # Don't fail the request if email fails
        
        return {"message": "Exam request updated successfully"}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating exam request: {e}")
        raise HTTPException(status_code=500, detail="Failed to update exam request")

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
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
