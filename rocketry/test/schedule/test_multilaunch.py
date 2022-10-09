import asyncio
import time

import pytest

from rocketry.tasks import FuncTask
from rocketry.exc import TaskTerminationException
from rocketry.conditions import SchedulerCycles, TaskStarted
from rocketry.args import TerminationFlag

from rocketry.conds import true

def run_slow_fail():
    time.sleep(5)
    raise

def run_slow_success():
    time.sleep(5)

def run_slow_threaded_fail(_thread_terminate_):
    time.sleep(0.2)
    if _thread_terminate_.is_set():
        raise TaskTerminationException
    else:
        raise

async def run_slow_async_fail():
    await asyncio.sleep(0.2)
    raise

async def run_success():
    await asyncio.sleep(0.1)

async def run_fail():
    await asyncio.sleep(0.1)
    raise RuntimeError("Oops")

def get_slow_func(execution):
    return {
        "async": run_slow_async_fail,
        "process": run_slow_fail,
        # Thread tasks are terminated inside the task (the task should respect _thread_terminate_)
        "thread": run_slow_threaded_fail,
    }[execution]

@pytest.mark.parametrize("execution", ["async", "thread", "process"])
def test_multilaunch_terminate(tmpdir, execution, session):
    # Start 5 time
    session.config.instant_shutdown = True
    session.config.max_process_count = 3

    func_run_slow = get_slow_func(execution)
    task = FuncTask(func_run_slow, name="slow task", start_cond=TaskStarted() <= 3, multilaunch=True, execution=execution, session=session)
    session.config.shut_cond = (TaskStarted(task="slow task") >= 3)
    session.start()

    logger = task.logger
    logs = [{"action": rec.action} for rec in logger.filter_by()]
    assert logs == [
        {"action": "run"},
        {"action": "run"},
        {"action": "run"},
        {"action": "terminate"},
        {"action": "terminate"},
        {"action": "terminate"},
    ]

@pytest.mark.parametrize("execution", ["async", "thread", "process"])
def test_multilaunch_terminate_end_cond(execution, session):
    # Start 5 time
    session.config.max_process_count = 3

    func_run_slow = get_slow_func(execution)
    task = FuncTask(func_run_slow, name="slow task", start_cond=TaskStarted() <= 3, end_cond=TaskStarted() == 3, multilaunch=True, execution=execution, session=session)
    session.config.shut_cond = (TaskStarted(task="slow task") >= 3)
    session.start()

    logger = task.logger
    logs = [{"action": rec.action} for rec in logger.filter_by()]
    assert logs == [
        {"action": "run"},
        {"action": "run"},
        {"action": "run"},
        {"action": "terminate"},
        {"action": "terminate"},
        {"action": "terminate"},
    ]

@pytest.mark.parametrize("status", ["success", "fail"])
@pytest.mark.parametrize("execution", ["async", "thread", "process"])
def test_multilaunch(execution, status, session):
    if execution == "process":
        pytest.skip(reason="Process too unreliable to test")
    # Start 5 time
    session.config.max_process_count = 3

    task = FuncTask(
        run_success if status == "success" else run_fail, 
        name="task", 
        start_cond=TaskStarted() <= 5,
        multilaunch=True,
        execution=execution, session=session
    )
    session.config.shut_cond = (TaskStarted(task="task") >= 3)
    session.start()

    logger = task.logger
    logs = [{"action": rec.action} for rec in logger.filter_by()]
    assert logs == [
        {"action": "run"},
        {"action": "run"},
        {"action": "run"},
        {"action": status},
        {"action": status},
        {"action": status},
    ]


def test_limited_processes(session):

    def run_thread(flag=TerminationFlag()):
        while not flag.is_set():
            ...

    async def run_async():
        while True:
            await asyncio.sleep(0)

    def do_post_check():
        sched = session.scheduler

        assert task_threaded.is_alive()
        assert task_threaded.is_running
        assert task_async.is_alive()
        assert task_async.is_running

        assert task1.is_alive()
        assert task2.is_alive()

        assert task1.is_running
        assert task2.is_running
        
        
        assert task1.n_alive == 3
        assert task2.n_alive == 1

        assert sched.n_alive == 7 # 3 processes, 1 thread, 1 async and this
        assert not sched.has_free_processors()

    task_threaded = FuncTask(run_thread, name="threaded", priority=4, start_cond=true, execution="thread", permanent=True, session=session)
    task_async = FuncTask(run_async, name="async", priority=4, start_cond=true, execution="async", permanent=True, session=session)
    post_check = FuncTask(do_post_check, name="post_check", on_shutdown=True, execution="main", session=session)

    task1 = FuncTask(run_slow_success, name="task_1", priority=3, start_cond=true, execution="process", session=session, multilaunch=True)
    task2 = FuncTask(run_slow_success, name="task_3", priority=1, start_cond=true, execution="process", session=session)

    session.config.max_process_count = 4
    session.config.instant_shutdown = True
    session.config.shut_cond = SchedulerCycles() >= 3

    session.start()

    outcome = post_check.logger.filter_by().all()[-1]
    assert outcome.action == "success", outcome.exc_text