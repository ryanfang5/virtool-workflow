from typing import Literal

State = Literal["WAITING", "STARTUP", "RUNNING", "CLEANUP", "FINISHED"]

WAITING = "WAITING"
STARTUP = "STARTUP"
RUNNING = "RUNNING"
CLEANUP = "CLEANUP"
FINISHED = "FINISHED"
ERROR = "ERROR"
