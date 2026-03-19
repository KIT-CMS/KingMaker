# Processor Class Inheritance Hierarchy

This diagram shows only the inheritance relationships (parent-child) between Python classes in `processor/`.
The top-most parent classes are from the `law` library.

## Legend

- **`<|--`** = Inheritance (solid triangle, child ← parent)

```mermaid
classDiagram
  direction TB

  %% LAW Library Base Classes
  class LawTask["law.Task"]
  class LawLocalWorkflow["law.LocalWorkflow"]
  class LawHTCondorWorkflow["law.htcondor.HTCondorWorkflow"]
  class LawWrapperTask["law.task.base.WrapperTask"]
  class LawRunOnceTask["law.tasks.RunOnceTask"]

  %% Framework Base Classes (from processor/framework.py)
  class Task
  class HTCondorWorkflow

  %% CROWN Base Classes
  class ProduceBase
  class CROWNExecuteBase
  class CROWNBuildBase

  %% CROWN Ntuple Production Tasks
  class ProduceSamples
  class CROWNRun
  class ConfigureDatasets
  class CROWNBuildCombined
  class CROWNBuild
  class BuildCROWNLib

  %% CROWN Friend Production Tasks
  class ProduceFriends
  class CROWNFriends
  class CROWNBuildFriend
  class QuantitiesMap

  %% CROWN Multi-Friend Production Tasks
  class ProduceMultiFriends
  class CROWNMultiFriends
  class CROWNBuildMultiFriend
  class FriendQuantitiesMap

  %% === INHERITANCE HIERARCHY ===

  %% Law library base classes
  LawTask <|-- Task
  LawHTCondorWorkflow <|-- HTCondorWorkflow
  Task <|-- HTCondorWorkflow

  %% Framework & CROWN base classes
  LawWrapperTask <|-- ProduceBase
  Task <|-- CROWNBuildBase
  Task <|-- ProduceBase
  LawLocalWorkflow <|-- CROWNExecuteBase
  HTCondorWorkflow <|-- CROWNExecuteBase

  %% CROWN Ntuple Production hierarchy
  ProduceBase <|-- ProduceSamples
  CROWNBuildBase <|-- CROWNBuildCombined
  CROWNBuildBase <|-- CROWNBuild
  CROWNExecuteBase <|-- CROWNRun
  Task <|-- ConfigureDatasets
  Task <|-- BuildCROWNLib

  %% CROWN Friend Production hierarchy
  ProduceBase <|-- ProduceFriends
  CROWNBuildBase <|-- CROWNBuildFriend
  CROWNExecuteBase <|-- CROWNFriends
  Task <|-- QuantitiesMap
  LawLocalWorkflow <|-- QuantitiesMap

  %% CROWN Multi-Friend Production hierarchy
  ProduceBase <|-- ProduceMultiFriends
  CROWNBuildBase <|-- CROWNBuildMultiFriend
  CROWNExecuteBase <|-- CROWNMultiFriends
  Task <|-- FriendQuantitiesMap
  LawLocalWorkflow <|-- FriendQuantitiesMap

```
