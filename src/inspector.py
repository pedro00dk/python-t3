import sys
import types
import traceback


class Inspector:
    """
    Inspects the received frame, building a snapshot from it.
    """

    def inspect(self, frame: types.FrameType, event: str, args, exec_call_frame: types.FrameType):
        snapshot = {}

        snapshot['type'] = event

        current_frame = frame
        frames = []
        while current_frame != exec_call_frame:
            frames.append(current_frame)
            current_frame = current_frame.f_back

        file = frame.f_code.co_filename
        frames = [frame for frame in frames if frame.f_code.co_filename == file]
        frames.reverse()
        snapshot['stack'] = [{'line': frame.f_lineno - 1, 'name': frame.f_code.co_name} for frame in frames]

        snapshot['heap'] = {}
        module = frames[-1].f_globals['__name__']
        classes = set()
        for i, frame in enumerate(frames):
            variables = frame.f_locals
            snapshot['stack'][i]['variables'] = [
                {'name': name, 'value': self._inspect_object(snapshot, variables[name], classes, module)}
                for name, value in variables.items() if not name.startswith('_')
            ]

        return snapshot

    def _inspect_object(self, snapshot: dict, obj, classes: set, module: str):
        if isinstance(obj, (bool, complex, type(None), str)):
            return str(obj)
        if isinstance(obj, (int, float)):
            if abs(obj) < 2 ** 53:
                return obj
            else:
                return str(obj)
        if isinstance(obj, type):
            if obj.__module__ == module:
                classes.add(obj)
            return str(obj)

        id_ = str(id(obj))
        if id_ in snapshot['heap']:
            return [id_]

        generic_type = 'other'
        language_type = type(obj).__name__
        user_defined = False
        members = None

        if isinstance(obj, (tuple, list, set)):
            generic_type = 'tuple' if isinstance(obj, tuple) else 'alist' if isinstance(obj, list) else 'set'
            members = [*enumerate(obj)]
        elif isinstance(obj, dict):
            generic_type = 'map'
            members = [*obj.items()]
        elif isinstance(obj, (*classes,)):
            user_defined = True
            members = [(key, value) for key, value in vars(obj).items() if not key.startswith('_')]
        else:
            # unknown object type
            pass

        if members is not None:
            # known object type
            # add id to snapshot heap (it has to be added before other objects inspections)
            obj = snapshot['heap'][id_] = {}
            obj['type'] = generic_type
            obj['languageType'] = language_type
            obj['userDefined'] = user_defined
            obj['members'] = [
                {
                    'key': self._inspect_object(snapshot, key, classes, module),
                    'value': self._inspect_object(snapshot, value, classes, module)
                }
                for key, value in members
            ]
            return [id_]
        else:
            # unknown object type
            # instead of inspecting unknown objects, I decided to inspect its type
            return self._inspect_object(snapshot, type(obj), classes, module)
