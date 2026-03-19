# Processor Class Hierarchy and Connections

This AI generated diagram shows Python classes in `processor/` and their inheritance hierarchy along with task dependency links.
The top-most parent classes are from the `law` library.

## Key Workflows

- **CROWN Ntuple Production**: `ProduceSamples` → `CROWNRun` ← `CROWNBuild` ← `BuildCROWNLib`
- **CROWN Friend Production**: `ProduceFriends` → `CROWNFriends` ← `CROWNBuildFriend` ← `QuantitiesMap` ← `CROWNRun`
- **CROWN Multi-Friend Production**: `ProduceMultiFriends` → `CROWNMultiFriends` combos `CROWNFriends` and `CROWNRun`

## Relationship Legend

- **`<|--`** = Inheritance (solid triangle)
- **`..>`** = Task dependency via `requires()` or `workflow_requires()` (dashed arrow)

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

  %% Utility / Example Tasks
  class CuHTask
  class SaveToRemote
  class RunRemote
  class ReadFromRemote

  %% === INHERITANCE HIERARCHY ===

  %% Law library base classes
  LawTask <|-- Task
  LawHTCondorWorkflow <|-- HTCondorWorkflow
  Task <|-- HTCondorWorkflow

  %% Framework & CROWN base classes
  LawWrapperTask <|-- ProduceBase
  Task <|-- ProduceBase
  LawLocalWorkflow <|-- CROWNExecuteBase
  HTCondorWorkflow <|-- CROWNExecuteBase
  Task <|-- CROWNBuildBase

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

  %% Utility & Example tasks
  HTCondorWorkflow <|-- CuHTask
  LawLocalWorkflow <|-- CuHTask
  Task <|-- SaveToRemote
  CuHTask <|-- RunRemote
  Task <|-- ReadFromRemote
  LawRunOnceTask <|-- ReadFromRemote

  %% === TASK DEPENDENCIES (requires/workflow_requires) ===

  %% CROWN Ntuple Production dependencies
  CROWNRun ..> ConfigureDatasets : requires/workflow_requires
  CROWNRun ..> CROWNBuild : requires/workflow_requires
  CROWNBuildCombined ..> BuildCROWNLib : requires
  CROWNBuild ..> CROWNBuildCombined : requires
  ProduceSamples ..> CROWNRun : requires

  %% CROWN Friend Production dependencies
  CROWNFriends ..> CROWNRun : workflow_requires
  CROWNFriends ..> CROWNBuildFriend : requires/workflow_requires
  CROWNBuildFriend ..> BuildCROWNLib : requires
  CROWNBuildFriend ..> QuantitiesMap : requires
  QuantitiesMap ..> CROWNRun : requires/workflow_requires
  ProduceFriends ..> CROWNFriends : requires

  %% CROWN Multi-Friend Production dependencies
  CROWNMultiFriends ..> CROWNRun : workflow_requires
  CROWNMultiFriends ..> CROWNBuildMultiFriend : requires/workflow_requires
  CROWNMultiFriends ..> CROWNFriends : workflow_requires
  CROWNBuildMultiFriend ..> BuildCROWNLib : requires
  CROWNBuildMultiFriend ..> FriendQuantitiesMap : requires
  FriendQuantitiesMap ..> CROWNRun : requires/workflow_requires
  FriendQuantitiesMap ..> CROWNFriends : requires/workflow_requires
  ProduceMultiFriends ..> CROWNMultiFriends : requires

  %% Example/Utility task dependencies
  RunRemote ..> SaveToRemote : requires/workflow_requires
  ReadFromRemote ..> RunRemote : requires
```
