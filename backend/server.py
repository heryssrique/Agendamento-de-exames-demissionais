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
    if session['expires_at'] < datetime.now(timezone.utc):
        await db.user_sessions.delete_one({"session_token": session_token})
        raise HTTPException(status_code=401, detail="Session expired")
    
    # Get user
    user = await db.users.find_one({"id": session['user_id']}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return User(**user)

async def require_department(required_dept: str):
    """Dependency to require specific department"""
    async def department_checker(current_user: User = Depends(get_current_user)):
        if current_user.department != required_dept:
            raise HTTPException(
                status_code=403,
                detail=f"Access denied. This action requires {required_dept} department"
            )
        return current_user
    return department_checker

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
        await db.user_sessions.insert_one(session.model_dump())
        
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
    """Set user's department (DP or RH)"""
    if dept.department not in ["DP", "RH"]:
        raise HTTPException(status_code=400, detail="Department must be 'DP' or 'RH'")
    
    await db.users.update_one(
        {"id": current_user.id},
        {"$set": {"department": dept.department}}
    )
    
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
        
        # Prepare update
        update_data = {k: v for k, v in update.model_dump().items() if v is not None}
        update_data['updated_at'] = datetime.now(timezone.utc)
        
        # Update database
        await db.exam_requests.update_one(
            {"id": exam_id},
            {"$set": update_data}
        )
        
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
