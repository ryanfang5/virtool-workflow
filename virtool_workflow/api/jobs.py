import asyncio
import traceback
import functools
import logging
from typing import Protocol, Optional

import aiohttp

from fixtures import fixture

from ..data_model import Job, Status, State
from .. import Workflow, WorkflowStep
from .errors import (
    JobAlreadyAcquired,
    JobsAPIServerError,
    raising_errors_by_status_code,
)

logger = logging.getLogger(__name__)


async def acquire_job_by_id(
    job_id: str, http: aiohttp.ClientSession, jobs_api_url: str, mem: int, proc: int
):
    """
    Acquire the job with a given ID using the jobs API.

    :param job_id: The id of the job to acquire
    :param http: An aiohttp.ClientSession to use to make the request.
    :param jobs_api_url: The url for the jobs API.

    :return: a :class:`virtool_workflow.data_model.Job` instance with an api key (.key attribute)
    """
    async with http.patch(
        f"{jobs_api_url}/jobs/{job_id}", json={"acquired": True}
    ) as response:
        async with raising_errors_by_status_code(
            response, status_codes_to_exceptions={"400": JobAlreadyAcquired}
        ) as document:
            logger.info(document)
            return Job(
                id=document["id"],
                args=document["args"],
                mem=document["mem"] if "mem" in document else mem,
                proc=document["proc"] if "proc" in document else proc,
                status=document["status"],
                workflow=document["workflow"],
                key=document["key"],
            )


@fixture
def acquire_job(http: aiohttp.ClientSession, jobs_api_url: str, mem: int, proc: int):
    async def _job_provider(job_id: str, retry=3, timeout=3):
        try:
            logger.debug(f"Acquiring {job_id}")
            return await acquire_job_by_id(job_id, http, jobs_api_url, mem, proc)
        except aiohttp.client_exceptions.ClientConnectionError as error:
            if retry > 0:
                await asyncio.sleep(timeout)
                return await _job_provider(job_id, retry=retry - 1)

        raise JobsAPIServerError("Unable to connect to server.")

    return _job_provider


class PushStatus(Protocol):
    async def __call__(
        self,
        state: State,
        step: WorkflowStep,
        error: str = None,
    ):
        """
        Update the job status.

        :param state: The current state of the workflow run.
        :param step: The current workflow step.
        :param error: An error message if applicable.
        """
        raise NotImplementedError()


@fixture(scope="function")
async def push_status(
    http, 
    job: Job,
    jobs_api_url: str,
    error: Optional[Exception],
    current_step: WorkflowStep,
    progress: float
):
    return functools.partial(
            _push_status, 
            http, 
            job, 
            jobs_api_url,
            step_name=current_step.display_name,
            step_description=current_step.description,
            stage=current_step.call.__name__,
            progress=progress,
            error=error,
    )


async def _push_status(
    http, 
    job: Job,
    jobs_api_url: str,
    step_name: str,
    step_description: str,
    stage: str,
    state: str, 
    progress: float,
    error: Exception = None, 
    max_tb: int = 50,
):
    async with http.post(
        f"{jobs_api_url}/jobs/{job.id}/status",
        json={
            "state": state,
            "stage": stage, 
            "step_name": step_name, 
            "step_description": step_description, 
            "error": {
                "type": error.__class__.__name__,
                "traceback": traceback.format_tb(error.__traceback__, max_tb),
                "details": [str(arg) for arg in error.args]
            } if error is not None else None,
            "progress": int(progress * 100),
        },
    ) as response:
        async with raising_errors_by_status_code(
            response, accept=[200, 201]
        ) as status_json:
            return Status(**status_json)
