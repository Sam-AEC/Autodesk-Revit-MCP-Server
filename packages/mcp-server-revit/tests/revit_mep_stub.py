"""Write-side stand-in for the Revit API, big enough to run the revit_mep scripts under CPython.

It builds on ``revit_api_stub`` (elements, connectors, collector, line protocol helpers) and adds what the write scripts
need: transactions with a real undo journal (so rollback can be checked), the Extensible Storage tag, Pipe/Duct creation
from points and connectors, the fitting calls, BreakCurve, ElectricalSystem and failure injection.

It is NOT Revit. It proves the scripts' control flow, the category guard, ownership/replace rules, rollback and the line
protocol; it cannot prove that Revit accepts the same calls (see the module docstring of revit_mep).
"""
from __future__ import annotations

import contextlib
import math
import sys
import types
from typing import Any, Callable, Dict, Iterator, List, Optional

import revit_api_stub as stub
from revit_api_stub import (
    App, Category, Connector, ElementId, FamilyInstance, Level, Line, MEPCurve, XYZ,
)

FT = 0.3048
WORLD: Dict[str, Any] = {"w": None}


# --------------------------------------------------------------------------- #
# Enumerations the scripts compare against
# --------------------------------------------------------------------------- #
class _Names:
    def __init__(self, *names: str) -> None:
        for n in names:
            setattr(self, n, n)


TransactionStatus = _Names("Started", "Committed", "RolledBack", "Pending")
FailureSeverity = _Names("Warning", "Error", "DeleteElements")
FailureProcessingResult = _Names("Continue", "ProceedWithRollBack")
PipeSystemType = _Names("UndefinedSystemType", "SupplyHydronic", "ReturnHydronic", "DomesticColdWater", "DomesticHotWater", "Sanitary", "Vent")
DuctSystemType = _Names("UndefinedSystemType", "SupplyAir", "ReturnAir", "ExhaustAir", "OtherAir")
ElectricalSystemType = _Names("UndefinedSystemType", "PowerCircuit", "Data")
BuiltInParameter = types.SimpleNamespace(
    **stub.BuiltInParameter.__dict__,
    RBS_PIPE_DIAMETER_PARAM="rbs_pipe_d", RBS_CURVE_DIAMETER_PARAM="rbs_duct_d", RBS_CURVE_WIDTH_PARAM="rbs_duct_w",
    RBS_CURVE_HEIGHT_PARAM="rbs_duct_h", RBS_PIPING_SYSTEM_TYPE_PARAM="rbs_pipe_sys", RBS_DUCT_SYSTEM_TYPE_PARAM="rbs_duct_sys",
    RBS_ELEC_CIRCUIT_NAME="rbs_circuit_name",
    ELEM_PARTITION_PARAM="elem_partition", ELEM_TYPE_PARAM="elem_type", WALL_BASE_CONSTRAINT="wall_base",
)
StorageType = _Names("None", "Integer", "Double", "String", "ElementId")
SpecTypeId = types.SimpleNamespace(Length="spec:length", Angle="spec:angle", Number="spec:number", String="spec:text",
                                   Reference="spec:ref", Boolean=types.SimpleNamespace(YesNo="spec:yesno"))
BuiltInCategory = types.SimpleNamespace(**stub.BuiltInCategory.__dict__, OST_ElectricalCircuits=-2001010)


def eid_of(e: Any) -> int:
    return e.Id.Value


class IFailuresPreprocessor:
    pass


class Guid:
    def __init__(self, text: str = "") -> None:
        self.text = str(text)

    @property
    def GUID(self) -> str:  # ExtensibleStorageFilter(schema.GUID)
        return self.text

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Guid) and other.text == self.text

    def __hash__(self) -> int:
        return hash(self.text)

    def __str__(self) -> str:
        return self.text


class _TypedAccess:
    """``entity.Set[String]("tag", value)`` / ``entity.Get[String]("tag")``."""

    def __init__(self, target: Callable[..., Any]) -> None:
        self.target = target

    def __getitem__(self, _: Any) -> Callable[..., Any]:
        return self.target


class Schema:
    registry: Dict[str, "Schema"] = {}

    def __init__(self, guid: Guid, name: str = "") -> None:
        self.GUID, self.name = guid, name

    @staticmethod
    def Lookup(guid: Guid) -> Optional["Schema"]:
        return Schema.registry.get(str(guid))


class SchemaBuilder:
    def __init__(self, guid: Guid) -> None:
        self.guid, self.name = guid, ""

    def SetSchemaName(self, name: str) -> None:
        self.name = name

    def SetVendorId(self, _: str) -> None: ...
    def SetReadAccessLevel(self, _: Any) -> None: ...
    def SetWriteAccessLevel(self, _: Any) -> None: ...
    def AddSimpleField(self, *_: Any) -> None: ...

    def Finish(self) -> Schema:
        schema = Schema(self.guid, self.name)
        Schema.registry[str(self.guid)] = schema
        return schema


class AccessLevel:
    Public = "Public"


class Entity:
    def __init__(self, schema: Schema) -> None:
        self.schema = schema
        self.values: Dict[str, Any] = {}
        self.Set = _TypedAccess(lambda k, v: self.values.__setitem__(k, v))
        self.Get = _TypedAccess(lambda k: self.values[k])

    def IsValid(self) -> bool:
        return True


class ExtensibleStorageFilter:
    def __init__(self, guid: Any) -> None:
        self.guid = guid


# --------------------------------------------------------------------------- #
# Elements
# --------------------------------------------------------------------------- #
class Param:
    """A writable parameter; every Set is journaled so a rollback restores it."""

    def __init__(self, owner: Any, key: str, value: Any, kind: str = "Double", read_only: bool = False) -> None:
        self.owner, self.key, self.value, self.StorageType, self.IsReadOnly = owner, key, value, kind, read_only
        self.HasValue = value is not None

    def Set(self, value: Any) -> bool:
        if self.IsReadOnly:
            return False
        old = self.value
        self.owner.apply_param(self.key, value)
        self.value = value
        WORLD["w"].log(lambda: (self.owner.apply_param(self.key, old), setattr(self, "value", old)))
        return True

    def AsString(self) -> Optional[str]:
        return self.value if isinstance(self.value, str) else None

    def AsDouble(self) -> float:
        return float(self.value)

    def AsElementId(self) -> ElementId:
        return ElementId(int(self.value))


class Taggable:
    """Extensible Storage entity + parameters of the elements the scripts create."""

    def _init_taggable(self) -> None:
        self.entity: Optional[Entity] = None
        self.parameters: Dict[str, Param] = {}

    def SetEntity(self, ent: Entity) -> None:
        old = self.entity
        self.entity = ent
        WORLD["w"].log(lambda: setattr(self, "entity", old))

    def GetEntity(self, schema: Schema) -> Entity:
        return self.entity if self.entity is not None and self.entity.schema is schema else Entity(schema)

    def get_Parameter(self, which: str) -> Optional[Param]:
        return self.parameters.get(which)

    def apply_param(self, key: str, value: Any) -> None:  # overridden by pipes (size -> connector radius)
        pass


class ParamDef:
    """Definition of a named parameter: its name, data type (SpecTypeId) and built-in id (None for a project parameter)."""

    def __init__(self, name: str, spec: str, bip: Any = None) -> None:
        self.Name, self.spec, self.BuiltInParameter = name, spec, bip

    def GetDataType(self) -> str:
        return self.spec


class NamedParam(Param):
    """A parameter found by name (revit_params). Set is journaled like Param; ``refuse`` makes Set return False."""

    def __init__(self, owner: Any, name: str, value: Any, kind: str, spec: str, read_only: bool = False, bip: Any = None) -> None:
        super().__init__(owner, name, value, kind, read_only)
        self.Definition = ParamDef(name, spec, bip)
        self.refuse = False

    def Set(self, value: Any) -> bool:
        if self.refuse:
            return False
        if self.StorageType == "ElementId":
            value = value.Value
        return super().Set(value)

    def AsInteger(self) -> int:
        return int(self.value)

    def AsElementId(self) -> ElementId:
        return ElementId(int(self.value) if self.value is not None else -1)

    def AsValueString(self) -> str:
        return "" if self.value is None else str(self.value)


class ParamElement(Taggable, stub.Element):
    """An element (or element type) with parameters by name, for the revit_params scripts."""

    def __init__(self, eid: int, category: Optional[Category], name: str = "", comments: str = "", level_id: int = -1, is_type: bool = False) -> None:
        stub.Element.__init__(self, eid, category, comments)
        self._init_taggable()
        self.Name, self.is_type, self.LevelId = name, is_type, ElementId(level_id)
        self.by_name: Dict[str, List[NamedParam]] = {}

    def add(self, name: str, value: Any, kind: str = "String", spec: str = "spec:text", read_only: bool = False, bip: Any = None) -> NamedParam:
        p = NamedParam(self, name, value, kind, spec, read_only, bip)
        self.by_name.setdefault(name, []).append(p)
        return p

    def GetParameters(self, name: str) -> List[NamedParam]:
        return list(self.by_name.get(name, []))

    def LookupParameter(self, name: str) -> Optional[NamedParam]:
        found = self.by_name.get(name)
        return found[0] if found else None

    @property
    def Parameters(self) -> List[NamedParam]:
        return [p for ps in self.by_name.values() for p in ps]

    def get_Parameter(self, which: Any) -> Any:
        for p in self.Parameters:
            if p.Definition.BuiltInParameter == which:
                return p
        return stub.Element.get_Parameter(self, which)

    def apply_param(self, key: str, value: Any) -> None:
        pass


class MepConnector(Connector):
    def __init__(self, domain: str, origin: tuple, system: str = "", radius_ft: float = 0.05, basis: tuple = (0.0, 0.0, 1.0),
                 direction: str = "Bidirectional", owner: Any = None, shape: str = "Round", width: float = 0.0, height: float = 0.0) -> None:
        super().__init__(domain=domain, kind="End", origin=origin, radius_ft=radius_ft, direction=direction, owner=owner,
                         shape=shape, width=width, height=height)
        self.CoordinateSystem = stub._CoordSys(basis)
        self.sys = system
        self.PipeSystemType = system if domain == "DomainPiping" else None
        self.DuctSystemType = system if domain == "DomainHvac" else None
        self.ElectricalSystemType = system if domain == "DomainElectrical" else None
        # the scripts read only the property that matches the domain; the others raise, as Revit does
        self._domain_prop = {"DomainPiping": "PipeSystemType", "DomainHvac": "DuctSystemType", "DomainElectrical": "ElectricalSystemType"}[domain]

    def __getattribute__(self, name: str) -> Any:
        if name in ("PipeSystemType", "DuctSystemType", "ElectricalSystemType"):
            if object.__getattribute__(self, "_domain_prop") != name:
                raise AttributeError(name)
            return object.__getattribute__(self, "sys")
        return object.__getattribute__(self, name)

    def set_system(self, system: str) -> None:
        old = self.sys
        self.sys = system
        WORLD["w"].log(lambda: setattr(self, "sys", old))

    def disconnect(self, other: "MepConnector") -> None:
        self.AllRefs.remove(other)
        other.AllRefs.remove(self)

        def undo() -> None:
            self.AllRefs.append(other)
            other.AllRefs.append(self)

        WORLD["w"].log(undo)

    def ConnectTo(self, other: "MepConnector") -> None:
        if other in self.AllRefs:
            return
        self.AllRefs.append(other)
        other.AllRefs.append(self)

        def undo() -> None:
            self.AllRefs.remove(other)
            other.AllRefs.remove(self)

        WORLD["w"].log(undo)


class ConnectorSet(list):
    pass


class ConnManager:
    def __init__(self, conns: List[MepConnector]) -> None:
        self.Connectors = ConnectorSet(conns)


class PipeLike(Taggable, MEPCurve):
    domain = "DomainPiping"
    kind_word = "pipe"
    cat_bic = stub.BuiltInCategory.OST_PipeCurves
    size_key = BuiltInParameter.RBS_PIPE_DIAMETER_PARAM
    sys_key = BuiltInParameter.RBS_PIPING_SYSTEM_TYPE_PARAM

    def __init__(self, eid: int, p0: tuple, p1: tuple, system: str, type_id: int, sys_type_id: int, level_id: int) -> None:
        MEPCurve.__init__(self, eid, Category(self.cat_bic, "Pipes" if self.kind_word == "pipe" else "Ducts"), [])
        self._init_taggable()
        self.Location = types.SimpleNamespace(Curve=Line(p0, p1))
        self.level_id = level_id
        self.diameter = 0.105
        self.width = 0.5
        self.height = 0.3
        d = _unit(p0, p1)
        self.c0 = MepConnector(self.domain, p0, system, 0.0525, basis=(-d[0], -d[1], -d[2]), owner=self)
        self.c1 = MepConnector(self.domain, p1, system, 0.0525, basis=d, owner=self)
        self.ConnectorManager = ConnManager([self.c0, self.c1])
        self.parameters = {
            self.sys_key: Param(self, self.sys_key, sys_type_id, "ElementId", True),
            stub.BuiltInParameter.ALL_MODEL_MARK: Param(self, stub.BuiltInParameter.ALL_MODEL_MARK, "", "String"),
        }
        self._add_size_params()

    def _add_size_params(self) -> None:
        k = self.size_key
        self.parameters[k] = Param(self, k, self.diameter)

    def apply_param(self, key: str, value: Any) -> None:
        if key == self.size_key:
            self.diameter = value
            for c in self.ConnectorManager.Connectors:
                if getattr(c, "kind_curve", True):
                    c.Radius = value / 2.0


class StubPipe(PipeLike):
    @staticmethod
    def Create(document: Any, *args: Any) -> "StubPipe":
        return WORLD["w"].create_curve(StubPipe, args)


class StubDuct(PipeLike):
    domain = "DomainHvac"
    kind_word = "duct"
    cat_bic = stub.BuiltInCategory.OST_DuctCurves
    size_key = BuiltInParameter.RBS_CURVE_DIAMETER_PARAM
    sys_key = BuiltInParameter.RBS_DUCT_SYSTEM_TYPE_PARAM

    def _add_size_params(self) -> None:
        self.parameters[BuiltInParameter.RBS_CURVE_DIAMETER_PARAM] = Param(self, BuiltInParameter.RBS_CURVE_DIAMETER_PARAM, self.diameter)
        self.parameters[BuiltInParameter.RBS_CURVE_WIDTH_PARAM] = Param(self, BuiltInParameter.RBS_CURVE_WIDTH_PARAM, self.width)
        self.parameters[BuiltInParameter.RBS_CURVE_HEIGHT_PARAM] = Param(self, BuiltInParameter.RBS_CURVE_HEIGHT_PARAM, self.height)

    def apply_param(self, key: str, value: Any) -> None:
        super().apply_param(key, value)
        if key in (BuiltInParameter.RBS_CURVE_WIDTH_PARAM, BuiltInParameter.RBS_CURVE_HEIGHT_PARAM):
            self.width, self.height = (value, self.height) if key == BuiltInParameter.RBS_CURVE_WIDTH_PARAM else (self.width, value)
            for c in self.ConnectorManager.Connectors:
                c.Shape, c.Width, c.Height = "Rectangular", self.width, self.height

    @staticmethod
    def Create(document: Any, *args: Any) -> "StubDuct":
        return WORLD["w"].create_curve(StubDuct, args)


class Fitting(Taggable, FamilyInstance):
    def __init__(self, eid: int, domain: str, connectors: List[MepConnector], word: str) -> None:
        bic = {"pipe": stub.BuiltInCategory.OST_PipeFitting, "duct": stub.BuiltInCategory.OST_DuctFitting}[word]
        FamilyInstance.__init__(self, eid, Category(bic, "Fittings"))
        self._init_taggable()
        self.parameters = {stub.BuiltInParameter.ALL_MODEL_MARK: Param(self, stub.BuiltInParameter.ALL_MODEL_MARK, "", "String")}
        self.MEPModel = types.SimpleNamespace(ConnectorManager=ConnManager(connectors))
        for c in connectors:
            c.Owner = self


class _ElementSet:
    def __init__(self, ids: List[int]) -> None:
        self.ids = ids

    @property
    def Size(self) -> int:
        return len(self.ids)


class StubElectricalSystem(Taggable, stub.Element):
    @staticmethod
    def Create(document: Any, ids: Any, system_type: str) -> "StubElectricalSystem":
        return WORLD["w"].create_circuit(list(ids), system_type)

    def __init__(self, eid: int, members: List[Any], system_type: str) -> None:
        stub.Element.__init__(self, eid, Category(stub.BuiltInCategory.OST_GenericModel, "Electrical Circuits"))
        self._init_taggable()
        self.members = members
        self.SystemType = system_type
        self.BaseEquipment: Any = None
        self.PanelName = ""
        self.CircuitNumber = ""
        self.parameters = {BuiltInParameter.RBS_ELEC_CIRCUIT_NAME: Param(self, BuiltInParameter.RBS_ELEC_CIRCUIT_NAME, "", "String")}

    @property
    def Elements(self) -> _ElementSet:
        return _ElementSet([eid_of(m) for m in self.members])

    def SelectPanel(self, panel: Any) -> None:
        old = (self.BaseEquipment, self.PanelName, self.CircuitNumber)
        self.BaseEquipment = panel
        self.PanelName = panel.get_Parameter(stub.BuiltInParameter.ALL_MODEL_MARK).AsString() or "panel"
        self.CircuitNumber = "1"
        WORLD["w"].log(lambda: (setattr(self, "BaseEquipment", old[0]), setattr(self, "PanelName", old[1]), setattr(self, "CircuitNumber", old[2])))

    def apply_param(self, key: str, value: Any) -> None:
        pass


class PipeType(stub.Element):
    def __init__(self, eid: int, name: str) -> None:
        super().__init__(eid, None)
        self.Name = name
        self.is_type = True


class DuctType(PipeType):
    pass


class PipingSystemType(PipeType):
    def __init__(self, eid: int, name: str, classification: str) -> None:
        super().__init__(eid, name)
        self.SystemClassification = classification


class MechanicalSystemType(PipingSystemType):
    pass


def _unit(p0: tuple, p1: tuple) -> tuple:
    d = (p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2])
    n = math.sqrt(sum(v * v for v in d)) or 1.0
    return (d[0] / n, d[1] / n, d[2] / n)


def _xyz(p: Any) -> tuple:
    return (p.X, p.Y, p.Z)


class Collector(stub.FilteredElementCollector):
    def WherePasses(self, flt: Any) -> "Collector":
        if isinstance(flt, ExtensibleStorageFilter):
            self._es = True
            return self
        super().WherePasses(flt)
        return self

    def __iter__(self) -> Iterator[Any]:
        if getattr(self, "_es", False):
            for e in list(self._doc.elements):
                if getattr(e, "entity", None) is not None:
                    yield e
            return
        yield from super().__iter__()


# --------------------------------------------------------------------------- #
# Transactions with an undo journal
# --------------------------------------------------------------------------- #
class _Opts:
    def __init__(self) -> None:
        self.pre: Any = None

    def SetFailuresPreprocessor(self, pre: Any) -> None:
        self.pre = pre


class _Accessor:
    def __init__(self, failures: List[Any]) -> None:
        self.failures = failures
        self.deleted: List[Any] = []

    def GetFailureMessages(self) -> List[Any]:
        return list(self.failures)

    def DeleteWarning(self, f: Any) -> None:
        self.deleted.append(f)


class Transaction:
    def __init__(self, document: Any, name: str = "") -> None:
        self.doc, self.name, self.mark, self.started = document, name, 0, False
        self.opts = _Opts()
        self.status = None

    def Start(self) -> None:
        self.mark, self.started = len(WORLD["w"].journal), True
        WORLD["w"].txn_log.append(("start", self.name))

    def GetFailureHandlingOptions(self) -> _Opts:
        return self.opts

    def SetFailureHandlingOptions(self, opts: _Opts) -> None:
        self.opts = opts

    def HasStarted(self) -> bool:
        return self.started

    def Commit(self) -> str:
        w = WORLD["w"]
        failures = w.commit_failures.get(self.name) or []
        for prefix, items in w.commit_failures.items():
            if prefix.endswith("*") and self.name.startswith(prefix[:-1]):
                failures = items
        if failures and self.opts.pre is not None:
            result = self.opts.pre.PreprocessFailures(_Accessor(list(failures)))
            if result == FailureProcessingResult.ProceedWithRollBack:
                self.RollBack()
                return TransactionStatus.RolledBack
        self.started = False
        w.txn_log.append(("commit", self.name))
        return TransactionStatus.Committed

    def RollBack(self) -> str:
        WORLD["w"].unwind(self.mark)
        self.started = False
        WORLD["w"].txn_log.append(("rollback", self.name))
        return TransactionStatus.RolledBack


class SubTransaction:
    def __init__(self, document: Any) -> None:
        self.status = None
        self.mark = 0

    def Start(self) -> None:
        self.mark, self.status = len(WORLD["w"].journal), TransactionStatus.Started

    def Commit(self) -> str:
        self.status = TransactionStatus.Committed
        return self.status

    def RollBack(self) -> str:
        WORLD["w"].unwind(self.mark)
        self.status = TransactionStatus.RolledBack
        return self.status

    def GetStatus(self) -> str:
        return self.status

    def Dispose(self) -> None: ...


class TransactionGroup:
    def __init__(self, document: Any, name: str = "") -> None:
        self.name, self.mark, self.started = name, 0, False

    def Start(self) -> None:
        self.mark, self.started = len(WORLD["w"].journal), True
        WORLD["w"].txn_log.append(("group_start", self.name))

    def HasStarted(self) -> bool:
        return self.started

    def Assimilate(self) -> str:
        self.started = False
        WORLD["w"].txn_log.append(("group_assimilate", self.name))
        return TransactionStatus.Committed

    def RollBack(self) -> str:
        WORLD["w"].unwind(self.mark)
        self.started = False
        WORLD["w"].txn_log.append(("group_rollback", self.name))
        return TransactionStatus.RolledBack


# --------------------------------------------------------------------------- #
# The document
# --------------------------------------------------------------------------- #
class _Creator:
    def __init__(self, world: "World") -> None:
        self.w = world

    def _fitting(self, word: str, conns: List[MepConnector], label: str) -> Fitting:
        w = self.w
        w.maybe_fail(label)
        origin = conns[0].Origin
        for c in conns[1:]:
            d = math.dist((origin.X, origin.Y, origin.Z), (c.Origin.X, c.Origin.Y, c.Origin.Z))
            if d > 1e-3:
                raise RuntimeError("the connectors are not at the same location (%.3f ft apart)" % d)
        for c in conns:
            if c.IsConnected:
                raise RuntimeError("a connector is already connected")
        domain = conns[0].Domain
        system = conns[0].sys
        fit_conns = [MepConnector(domain, _xyz(c.Origin), system, c.Radius, shape=c.Shape, width=c.Width, height=c.Height) for c in conns]
        f = Fitting(w.next_id(), domain, fit_conns, word)
        w.add(f)
        for c, fc in zip(conns, fit_conns):
            c.ConnectTo(fc)
        w.fittings.append((label, f))
        return f

    def _word(self, c: MepConnector) -> str:
        return "pipe" if c.Domain == "DomainPiping" else "duct"

    def NewElbowFitting(self, a: MepConnector, b: MepConnector) -> Fitting:
        return self._fitting(self._word(a), [a, b], "elbow")

    def NewUnionFitting(self, a: MepConnector, b: MepConnector) -> Fitting:
        return self._fitting(self._word(a), [a, b], "union")

    def NewTransitionFitting(self, a: MepConnector, b: MepConnector) -> Fitting:
        return self._fitting(self._word(a), [a, b], "transition")

    def NewTeeFitting(self, a: MepConnector, b: MepConnector, c: MepConnector) -> Fitting:
        return self._fitting(self._word(a), [a, b, c], "tee")

    def NewTakeoffFitting(self, branch: MepConnector, trunk: Any) -> Fitting:
        w = self.w
        w.maybe_fail("takeoff")
        tap = MepConnector(branch.Domain, _xyz(branch.Origin), branch.sys, branch.Radius, owner=trunk)
        tap.kind_curve = False
        trunk.ConnectorManager.Connectors.append(tap)
        w.log(lambda: trunk.ConnectorManager.Connectors.remove(tap))
        own = MepConnector(branch.Domain, _xyz(branch.Origin), branch.sys, branch.Radius)
        f = Fitting(w.next_id(), branch.Domain, [own], self._word(branch))
        w.add(f)
        branch.ConnectTo(own)
        tap.ConnectTo(MepConnector(branch.Domain, _xyz(branch.Origin), branch.sys, branch.Radius, owner=f))
        w.fittings.append(("takeoff", f))
        return f


class World(stub.Document):
    """A model plus an undo journal. ``fail_on`` maps an API label to a function(count) -> bool that makes it raise."""

    def __init__(self) -> None:
        super().__init__([])
        self.journal: List[Callable[[], None]] = []
        self.txn_log: List[tuple] = []
        self.commit_failures: Dict[str, List[Any]] = {}
        self.fail_on: Dict[str, Callable[[int], bool]] = {}
        self.calls: Dict[str, int] = {}
        self.fittings: List[tuple] = []
        self.cascade: Dict[int, List[int]] = {}
        self._next = 5000
        self.Create = _Creator(self)

    # -- journal -------------------------------------------------------------- #
    def log(self, undo: Callable[[], None]) -> None:
        self.journal.append(undo)

    def unwind(self, mark: int) -> None:
        while len(self.journal) > mark:
            self.journal.pop()()

    def next_id(self) -> int:
        self._next += 1
        return self._next

    def maybe_fail(self, label: str) -> None:
        self.calls[label] = self.calls.get(label, 0) + 1
        rule = self.fail_on.get(label)
        if rule is not None and rule(self.calls[label]):
            raise RuntimeError("Revit refused %s (call %d)" % (label, self.calls[label]))

    def add(self, e: Any) -> Any:
        self.elements.append(e)
        self.log(lambda: self.elements.remove(e))
        return e

    # -- building a scene ----------------------------------------------------- #
    def level(self, name: str, elevation_ft: float) -> Level:
        lv = Level(self.next_id(), name, elevation_ft)
        self.elements.append(lv)
        return lv

    def equipment(self, mark: str, bic: int, ports: List[Dict[str, Any]], category_name: str = "Equipment") -> FamilyInstance:
        """ports: dict(domain, system, origin, basis, radius_ft, direction)."""
        conns = [MepConnector(p.get("domain", "DomainPiping"), p["origin"], p.get("system", ""), p.get("radius_ft", 0.05),
                              p.get("basis", (0.0, 0.0, 1.0)), p.get("direction", "Bidirectional"), None,
                              p.get("shape", "Round"), p.get("width", 0.0), p.get("height", 0.0)) for p in ports]
        inst = FamilyInstance(self.next_id(), Category(bic, category_name), comments="")
        inst.set_param(stub.BuiltInParameter.ALL_MODEL_MARK, mark)
        circuits: List[Any] = []
        inst.MEPModel = types.SimpleNamespace(ConnectorManager=ConnManager(conns), GetElectricalSystems=lambda: list(circuits))
        inst.circuits = circuits
        for c in conns:
            c.Owner = inst
        self.elements.append(inst)
        return inst

    def pipe_type(self, name: str) -> PipeType:
        t = PipeType(self.next_id(), name)
        self.elements.append(t)
        return t

    def duct_type(self, name: str) -> DuctType:
        t = DuctType(self.next_id(), name)
        self.elements.append(t)
        return t

    def system_type(self, name: str, classification: str, duct: bool = False) -> Any:
        t = (MechanicalSystemType if duct else PipingSystemType)(self.next_id(), name, classification)
        self.elements.append(t)
        return t

    # -- API behaviour -------------------------------------------------------- #
    def Delete(self, element_id: ElementId) -> List[ElementId]:
        self.maybe_fail("delete")
        victims = [element_id.Value] + list(self.cascade.get(element_id.Value, []))
        done: List[ElementId] = []
        for v in victims:
            e = self.GetElement(ElementId(v))
            if e is None:
                continue
            self._remove(e)
            done.append(ElementId(v))
        return done

    def _remove(self, e: Any) -> None:
        links = []
        for c in getattr(e, "ConnectorManager", types.SimpleNamespace(Connectors=[])).Connectors:
            for other in list(c.AllRefs):
                links.append((c, other))
                c.AllRefs.remove(other)
                other.AllRefs.remove(c)
        circuits = getattr(e, "members", None)
        idx = self.elements.index(e)
        self.elements.remove(e)

        def undo() -> None:
            self.elements.insert(idx, e)
            for c, other in links:
                c.AllRefs.append(other)
                other.AllRefs.append(c)

        self.log(undo)
        if circuits is not None:
            # the members leave the circuit
            for m in circuits:
                if e in m.circuits:
                    m.circuits.remove(e)
                    self.log(lambda m=m: m.circuits.append(e))

    def create_curve(self, cls: type, args: tuple) -> PipeLike:
        self.maybe_fail("create_" + cls.kind_word)
        word = cls.kind_word
        # overloads: (typeId, levelId, Connector a, Connector|XYZ b)  or  (systemTypeId, typeId, levelId, XYZ a, XYZ b)
        if len(args) == 4:
            type_id, level_id, a, b = args
            sys_name, sys_type_id = a.sys, self._system_type_id_for(a.sys, word)
            p0 = _xyz(a.Origin)
            p1 = _xyz(b.Origin) if hasattr(b, "Origin") else _xyz(b)
            cu = cls(self.next_id(), p0, p1, sys_name, type_id.Value, sys_type_id, level_id.Value)
            self.add(cu)
            a.ConnectTo(cu.c0)
            if hasattr(b, "Origin"):
                b.ConnectTo(cu.c1)
            return cu
        sys_id, type_id, level_id, a, b = args
        st = self.GetElement(sys_id)
        cu = cls(self.next_id(), _xyz(a), _xyz(b), st.SystemClassification, type_id.Value, sys_id.Value, level_id.Value)
        self.add(cu)
        return cu

    def _system_type_id_for(self, classification: str, word: str) -> int:
        for e in self.elements:
            if isinstance(e, PipingSystemType) and e.SystemClassification == classification and (isinstance(e, MechanicalSystemType) == (word == "duct")):
                return e.Id.Value
        return -1

    def break_curve(self, cls_word: str, element_id: ElementId, point: Any) -> ElementId:
        self.maybe_fail("break_curve")
        cu = self.GetElement(element_id)
        p0, p1 = _xyz(cu.Location.Curve.p0), _xyz(cu.Location.Curve.p1)
        p = _xyz(point)
        cls = type(cu)
        new = cls(self.next_id(), p, p1, cu.c1.sys, 0, int(cu.parameters[cls.sys_key].value), cu.level_id)
        new.diameter = cu.diameter
        new.parameters[cls.size_key].value = cu.diameter
        for c in new.ConnectorManager.Connectors:
            c.Radius = cu.diameter / 2.0
        old_line = cu.Location.Curve
        cu.Location.Curve = Line(p0, p)
        moved = list(cu.c1.AllRefs)
        for other in moved:
            cu.c1.AllRefs.remove(other)
            other.AllRefs.remove(cu.c1)
            new.c1.AllRefs.append(other)
            other.AllRefs.append(new.c1)
        old_origin = cu.c1.Origin
        cu.c1.Origin = XYZ(*p)
        self.add(new)

        def undo() -> None:
            cu.Location.Curve = old_line
            cu.c1.Origin = old_origin
            for other in moved:
                new.c1.AllRefs.remove(other)
                other.AllRefs.remove(new.c1)
                cu.c1.AllRefs.append(other)
                other.AllRefs.append(cu.c1)

        self.log(undo)
        return new.Id

    def create_circuit(self, ids: List[ElementId], system_type: str) -> StubElectricalSystem:
        self.maybe_fail("create_circuit")
        members = [self.GetElement(i) for i in ids]
        es = StubElectricalSystem(self.next_id(), members, system_type)
        self.add(es)
        for m in members:
            m.circuits.append(es)
            self.log(lambda m=m, es=es: m.circuits.remove(es) if es in m.circuits else None)
        return es

    def GetElement(self, element_id: Any) -> Any:  # accepts ElementId or int
        value = element_id.Value if hasattr(element_id, "Value") else int(element_id)
        for e in self.elements:
            if e.Id.Value == value:
                return e
        return None

    # -- running a script ----------------------------------------------------- #
    def run(self, script: str) -> str:
        scope: Dict[str, Any] = {"doc": self, "app": App(), "__output__": "", "__name__": "__ipy__"}
        exec(compile(script, "<embedded-script>", "exec"), scope)  # noqa: S102 - test-only stub execution
        return str(scope["__output__"])

    def snapshot(self) -> tuple:
        """Everything a rollback must restore, in a comparable form."""
        return (
            sorted(e.Id.Value for e in self.elements),
            sorted((e.Id.Value, tuple(sorted((id(r)) for c in getattr(e, "ConnectorManager", types.SimpleNamespace(Connectors=[])).Connectors for r in c.AllRefs)))
                   for e in self.elements if hasattr(e, "ConnectorManager")),
            sorted((e.Id.Value, str(e.entity.values) if getattr(e, "entity", None) else "") for e in self.elements if hasattr(e, "entity")),
        )


@contextlib.contextmanager
def installed_mep(monkeypatch: Any) -> Iterator[World]:
    """Make ``import clr / System / Autodesk.Revit.DB(.Plumbing/.Mechanical/.Electrical/.ExtensibleStorage)`` resolve here."""
    world = World()
    WORLD["w"] = world
    Schema.registry.clear()
    db = types.ModuleType("Autodesk.Revit.DB")
    for name in ("XYZ", "ElementId", "BuiltInCategory", "Options", "ViewDetailLevel", "Level", "Line", "MEPCurve", "FamilyInstance",
                 "Family", "FamilySymbol", "ElementMulticategoryFilter", "FamilyInstanceFilter", "Connector", "Category"):
        setattr(db, name, getattr(stub, name, None))
    db.BuiltInCategory = BuiltInCategory
    db.BuiltInParameter = BuiltInParameter
    db.FilteredElementCollector = Collector
    db.Transaction, db.TransactionGroup, db.SubTransaction = Transaction, TransactionGroup, SubTransaction
    db.TransactionStatus, db.FailureSeverity, db.FailureProcessingResult = TransactionStatus, FailureSeverity, FailureProcessingResult
    db.IFailuresPreprocessor = IFailuresPreprocessor
    db.Domain = _Names("DomainPiping", "DomainHvac", "DomainElectrical")
    db.StorageType, db.SpecTypeId = StorageType, SpecTypeId
    plumbing = types.ModuleType("Autodesk.Revit.DB.Plumbing")
    plumbing.Pipe, plumbing.PipeType, plumbing.PipingSystemType = StubPipe, PipeType, PipingSystemType
    plumbing.PipeSystemType = PipeSystemType
    plumbing.PlumbingUtils = types.SimpleNamespace(BreakCurve=lambda document, element_id, point: world.break_curve("pipe", element_id, point))
    mechanical = types.ModuleType("Autodesk.Revit.DB.Mechanical")
    mechanical.Duct, mechanical.DuctType, mechanical.MechanicalSystemType = StubDuct, DuctType, MechanicalSystemType
    mechanical.DuctSystemType = DuctSystemType
    mechanical.MechanicalUtils = types.SimpleNamespace(BreakCurve=lambda document, element_id, point: world.break_curve("duct", element_id, point))
    electrical = types.ModuleType("Autodesk.Revit.DB.Electrical")
    electrical.ElectricalSystem, electrical.ElectricalSystemType = StubElectricalSystem, ElectricalSystemType
    storage = types.ModuleType("Autodesk.Revit.DB.ExtensibleStorage")
    storage.Schema, storage.SchemaBuilder, storage.AccessLevel = Schema, SchemaBuilder, AccessLevel
    storage.Entity, storage.ExtensibleStorageFilter = Entity, ExtensibleStorageFilter
    system = types.ModuleType("System")
    system.Guid = Guid
    system.String = str
    diagnostics = types.ModuleType("System.Diagnostics")
    diagnostics.Stopwatch = stub.Stopwatch
    generic = types.ModuleType("System.Collections.Generic")
    generic.List = stub._GenericList()
    modules = {
        "clr": types.ModuleType("clr"),
        "System": system,
        "System.Collections": types.ModuleType("System.Collections"),
        "System.Collections.Generic": generic,
        "System.Diagnostics": diagnostics,
        "Autodesk": types.ModuleType("Autodesk"),
        "Autodesk.Revit": types.ModuleType("Autodesk.Revit"),
        "Autodesk.Revit.DB": db,
        "Autodesk.Revit.DB.Plumbing": plumbing,
        "Autodesk.Revit.DB.Mechanical": mechanical,
        "Autodesk.Revit.DB.Electrical": electrical,
        "Autodesk.Revit.DB.ExtensibleStorage": storage,
    }
    modules["clr"].GetClrType = lambda t: t  # type: ignore[attr-defined]
    for name, mod in modules.items():
        monkeypatch.setitem(sys.modules, name, mod)
    try:
        yield world
    finally:
        WORLD["w"] = None
        Schema.registry.clear()
