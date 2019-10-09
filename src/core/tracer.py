import multiprocessing as mp
import sys
import types

import events
from . import inspector
from . import scope


class Tracer:
    """
    Traces python script and analyses its state after every instruction.
    """

    @staticmethod
    def init_run(name: str, script: str, sandbox: bool, action_queue: mp.Queue, result_queue: mp.Queue):
        """
        Initializes the tracer and run it in a single function, usefull to start the tracer in a separated process.
        """
        Tracer(name, script, sandbox, action_queue, result_queue).run()

    def __init__(self, name: str, script: str, sandbox: bool, action_queue: mp.Queue, result_queue: mp.Queue):
        """
        Initializes the tracer with the script name, python script and sandbox flag.
        """
        self._name = name
        self._script = script
        self._sandbox = sandbox
        self._action_queue = action_queue
        self._result_queue = result_queue
        self._lines = self._script.splitlines() if len(script) > 0 else ['']

    def run(self):
        """
        Configures the scope and runs the tracer, giving the tracing control to the frame processor.
        """
        script_scope = scope.default_scope(self._name) if not self._sandbox else scope.sandbox_scope(self._name)
        frame_processor = FrameProcessor(self._name, self._lines, self._action_queue, self._result_queue)

        try:
            action = self._action_queue.get()
            compiled = compile(self._script, script_scope[scope.Globals.FILE], 'exec')
            self._result_queue.put(events.Event(events.Results.STARTED))
            sys.settrace(frame_processor.trace)
            exec(compiled, script_scope)
        except Exception as e:
            self._result_queue.put(events.Event(events.Results.ERROR, str(e)))
        finally:
            sys.settrace(None)


class FrameProcessor:
    """
    Read action queue waiting for actions, process the frames and write the results in the queue. 
    """

    def __init__(self, name: str, lines: list, action_queue: mp.Queue, result_queue: mp.Queue):
        """
        Initializes the frame processor with the script name, lines and queues.
        """
        self._name = name
        self._lines = lines
        self._action_queue = action_queue
        self._result_queue = result_queue

        # frame common info
        self.exec_call_frame = None
        self.inspected_frame_count = 0

    def trace(self, frame: types.FrameType, event: str, args):
        """
        The script trace function.
        """
        if not FrameUtil.is_file(frame, self._name) or not FrameUtil.is_traceable(event):
            return self.trace

        self.exec_call_frame = frame.f_back if self.inspected_frame_count == 0 else self.exec_call_frame
        self.inspected_frame_count += 1

        while True:
            action = self._action_queue.get()

            # hold actions
            if action.name == events.Actions.EVAL:
                expression = action.value['expression']
                inspect = action.value['inspect']

                # evaluate first and then inspect state
                product = self.evaluate_expression(frame, expression)
                inspection = {}  # self.inspect_state(frame, event, args) if inspect else {}

                self._result_queue.put(events.Event(events.Results.PRODUCT, {**inspection, **product}))
                continue

            # progressive actions
            if action.name == events.Actions.STEP:
                self._result_queue.put(events.Event(events.Results.DATA, {'finish': True}))
            elif action.name == events.Actions.QUIT:
                self._result_queue.put(events.Event(events.Results.DATA, {}))
            break

        return self.trace

    # evaluation methods

    def evaluate_expression(self, frame: types.FrameType, expression: str):
        """
        Evaluates expressions against the frame scope, process possible exceptions if any is thrown.
        The expression is able to mutate the script state.
        """
        try:
            product = eval(expression, frame.f_globals, frame.f_locals)
        except Exception as e:
            product = {
                'type': type(e).__name__,
                'value': e.args,
                'traceback': traceback.format_exception(type(e), e, e.__traceback__)
            }
            pass
        finally:
            return {'product': product}


class FrameUtil:
    """
    Utility objects and functions for processing frames.
    """

    # list of traceable events
    TRACEABLE_EVENTS = {'call', 'line', 'exception', 'return'}

    @staticmethod
    def is_file(frame: types.FrameType, name: str):
        """
        Returns true if the frame is from the received file name.
        """
        return frame.f_code.co_filename == name

    @staticmethod
    def is_traceable(event: str):
        """
        Returns true if the frame event is traceable.
        """
        return event in FrameUtil.TRACEABLE_EVENTS
