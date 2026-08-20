import time
import logging
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from app.config import settings

logger = logging.getLogger(__name__)

class WorkstationAgent(BaseModel):
    agent_id: str
    ip_address: str
    user_name: str
    app_name: str = "Autodesk Inventor"
    status: str = "READY"  # READY, BUSY, OFFLINE
    last_heartbeat: float = Field(default_factory=time.time)
    active_job_id: Optional[str] = None
    queue_name: str = ""

class AgentRouter:
    """
    Manages connected Autodesk workstation agents and guarantees safe,
    sequential job dispatch per engineering workstation queue.
    """

    def __init__(self):
        self._agents: Dict[str, WorkstationAgent] = {}
        # Pre-register default workstation per specification
        self.register_agent(
            agent_id="mech-pc-150",
            ip_address=settings.DEFAULT_WORKSTATION_IP,
            user_name=settings.DEFAULT_USER_NAME,
            app_name="Autodesk Inventor"
        )

    def register_agent(self, agent_id: str, ip_address: str, user_name: str, app_name: str = "Autodesk Inventor") -> WorkstationAgent:
        agent = WorkstationAgent(
            agent_id=agent_id,
            ip_address=ip_address,
            user_name=user_name,
            app_name=app_name,
            status="READY",
            last_heartbeat=time.time(),
            queue_name=f"queue:autodesk:{ip_address}"
        )
        self._agents[agent_id] = agent
        logger.info(f"Registered Autodesk workstation: {agent_id} ({ip_address}) for {user_name}")
        return agent

    def list_agents(self) -> List[WorkstationAgent]:
        now = time.time()
        for agent in self._agents.values():
            if now - agent.last_heartbeat > 60:
                agent.status = "OFFLINE"
        return list(self._agents.values())

    def get_agent_by_ip(self, ip_address: str) -> Optional[WorkstationAgent]:
        for agent in self._agents.values():
            if agent.ip_address == ip_address:
                return agent
        return None

    def heartbeat(self, agent_id: str):
        if agent_id in self._agents:
            self._agents[agent_id].last_heartbeat = time.time()
            if self._agents[agent_id].status == "OFFLINE":
                self._agents[agent_id].status = "READY"

    def acquire_lock(self, ip_address: str, job_id: str) -> bool:
        agent = self.get_agent_by_ip(ip_address)
        if not agent or agent.status == "BUSY":
            return False
        agent.status = "BUSY"
        agent.active_job_id = job_id
        return True

    def release_lock(self, ip_address: str):
        agent = self.get_agent_by_ip(ip_address)
        if agent:
            agent.status = "READY"
            agent.active_job_id = None

agent_router = AgentRouter()
