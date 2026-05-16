import asyncio
import json
import sys
from typing import Any, Callable

from otree.channels import utils as channel_utils

from .utils import log_function


class BotTask:
    def __int__(self):
        self.get_session = None
        self.config = None
        self.add_debug_log = None
        self.store_send_data = None
        raise RuntimeError

    @staticmethod
    def _unlock_interface(group_name: str):
        log_function(__class__, sys._getframe().f_code.co_name)

        asyncio.create_task(channel_utils.group_send(
            group=group_name, data={'unblock': True}))

    @classmethod
    def ensure_exception_handler(cls):
        loop = asyncio.get_running_loop()
        if loop.get_exception_handler() is None:
            loop.set_exception_handler(cls.exception_handler)

    @staticmethod
    def exception_handler(loop, context: dict[str, Any]):
        print(f"\nexception_handler:\n{context['exception']}\n")

        # Exceptions in the callback_handler do not pass the task
        if 'future' not in context.keys():
            return

        name = 'no name'
        try:
            task = context['future']
            name = task.get_name()
            data = json.loads(name)

            # Unblocked the interface if there is an exception in the task
            group_name = data['group_name']
            BotTask._unlock_interface(group_name)
        except Exception as e:
            print(f"\nError in exception_handler\n{name}\n{e}\n")

    @staticmethod
    def callback_handler(task: asyncio.Task):
        from .session_patch import Queues

        if task.exception():
            print(f"\nBot task failed:\n{task.exception()}\n")

        data = json.loads(task.get_name())
        llm_host = data.get('llm_host')
        if not llm_host:
            return

        async def release():
            await Queues.release(
                data['session_code'], data['round_number'], llm_host)

        asyncio.create_task(release())

    async def start_task(self, coro: Callable):
        log_function(__class__, sys._getframe().f_code.co_name)

        from .session_patch import Queues

        self.ensure_exception_handler()
        llm_host = await Queues.acquire(
            self.config['session_code'], self.config['round_number'])
        self.config['llm_host'] = llm_host

        if llm_host is None:
            self.add_debug_log(
                f"No LLM host available for: {self.config['idx']}")
            self.store_send_data(
                llm_output="I am sorry, could you repeat that?")
            self._unlock_interface(self.config['group_name'])
        else:
            # Needed by the exception handler and callback handler
            data = {'llm_host': llm_host,
                    'group_name': self.config['group_name'],
                    'session_code': self.config['session_code'],
                    'round_number': self.config['round_number']}
            task = asyncio.create_task(coro())
            task.set_name(json.dumps(data))
            task.add_done_callback(self.callback_handler)
