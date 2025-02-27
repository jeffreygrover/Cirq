# Copyright 2019 The Cirq Developers
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Sequence, TYPE_CHECKING

import sympy
from google.protobuf import json_format

from cirq.api.google import v2

from cirq.google.api import v2 as api_v2
from cirq.google import arg_func_langs

if TYPE_CHECKING:
    import cirq


@dataclass(frozen=True)
class DeserializingArg:
    """Specification of the arguments to deserialize an argument to a gate.

    Args:
        serialized_name: The serialized name of the gate that is being
            deserialized.
        constructor_arg_name: The name of the argument in the constructor of
            the gate corresponding to this serialized argument.
        value_func: Sometimes a value from the serialized proto needs to
            converted to an appropriate type or form. This function takes the
            serialized value and returns the appropriate type. Defaults to
            None.
        required: Whether a value must be specified when constructing the
            deserialized gate. Defaults to True.
    """
    serialized_name: str
    constructor_arg_name: str
    value_func: Optional[Callable[[arg_func_langs.ArgValue], Any]] = None
    required: bool = True


class GateOpDeserializer:
    """Describes how to deserialize a proto to a given Gate type.

    Attributes:
        serialized_gate_id: The id used when serializing the gate.
    """

    def __init__(self,
                 serialized_gate_id: str,
                 gate_constructor: Callable,
                 args: Sequence[DeserializingArg],
                 num_qubits_param: Optional[str] = None):
        """Constructs a deserializer.

        Args:
            serialized_gate_id: The serialized id of the gate that is being
                deserialized.
            gate_constructor: A function that produces the deserialized gate
                given arguments from args.
            args: A list of the arguments to be read from the serialized
                gate and the information required to use this to construct
                the gate using the gate_constructor above.
            num_qubits_param: Some gate constructors require that the number
                of qubits be passed to their constructor. This is the name
                of the parameter in the constructor for this value. If None,
                no number of qubits is passed to the constructor.
        """
        self.serialized_gate_id = serialized_gate_id
        self.gate_constructor = gate_constructor
        self.args = args
        self.num_qubits_param = num_qubits_param

    def from_proto_dict(self, proto: Dict) -> 'cirq.GateOperation':
        """Turns a cirq.api.google.v2.Operation proto into a GateOperation."""
        msg = v2.program_pb2.Operation()
        json_format.ParseDict(proto, msg)
        return self.from_proto(msg)

    def from_proto(self,
                   proto: v2.program_pb2.Operation) -> 'cirq.GateOperation':
        """Turns a cirq.api.google.v2.Operation proto into a GateOperation."""
        qubits = [api_v2.grid_qubit_from_proto_id(q.id) for q in proto.qubits]
        args = self._args_from_proto(proto)
        if self.num_qubits_param is not None:
            args[self.num_qubits_param] = len(qubits)
        gate = self.gate_constructor(**args)
        return gate.on(*qubits)

    def _args_from_proto(self, proto: v2.program_pb2.Operation
                        ) -> Dict[str, arg_func_langs.ArgValue]:
        return_args = {}
        for arg in self.args:
            if arg.serialized_name not in proto.args and arg.required:
                raise ValueError(
                    'Argument {} not in deserializing args, but is required.'.
                    format(arg.serialized_name))

            value = None  # type: Optional[arg_func_langs.ArgValue]
            if arg.serialized_name in proto.args:
                arg_proto = proto.args[arg.serialized_name]
                which = arg_proto.WhichOneof('arg')
                if which == 'arg_value':
                    arg_value = arg_proto.arg_value
                    which_val = arg_value.WhichOneof('arg_value')
                    if which_val == 'float_value':
                        value = float(arg_value.float_value)
                    elif which_val == 'bool_values':
                        value = arg_value.bool_values.values
                    elif which_val == 'string_value':
                        value = str(arg_value.string_value)
                elif which == 'symbol':
                    value = sympy.Symbol(arg_proto.symbol)

            if value is None and arg.required:
                raise ValueError(
                    'Could not get arg {} from arg_proto {}'.format(
                        arg.serialized_name, proto.args))

            if arg.value_func is not None:
                value = arg.value_func(value)

            if value is not None:
                return_args[arg.constructor_arg_name] = value
        return return_args
