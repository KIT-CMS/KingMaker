# Processor Task Dependencies

This diagram shows only the task dependencies (requires/workflow_requires) between Python classes in `processor/`.
These are the actual execution flow dependencies that determine task ordering.

## Legend

- **`..>`** = Task dependency via `requires()` or `workflow_requires()` (dashed arrow)
- **`(Workflow)`** = Workflow task inheriting from `HTCondorWorkflow` (executes on remote cluster)
- **`(Local)`** = Local task (does not inherit from `HTCondorWorkflow`)

## Key Task Flows

### CROWN Ntuple Production
```
ProduceSamples 
  → CROWNRun 
    ← CROWNBuild 
      ← BuildCROWNLib
    ← ConfigureDatasets
```

### CROWN Friend Production
```
ProduceFriends 
  → CROWNFriends 
    ← CROWNBuildFriend 
      ← BuildCROWNLib
      ← QuantitiesMap 
        ← CROWNRun
```

### CROWN Multi-Friend Production
```
ProduceMultiFriends 
  → CROWNMultiFriends 
    ← CROWNRun
    ← CROWNBuildMultiFriend 
      ← BuildCROWNLib
      ← FriendQuantitiesMap 
        ← CROWNRun
        ← CROWNFriends
    ← CROWNFriends
```


```mermaid
classDiagram
  direction TB

  %% CROWN Ntuple Production Tasks
  class ProduceSamples["ProduceSamples (Local)"]
  class CROWNRun["CROWNRun (Workflow)"]
  class ConfigureDatasets["ConfigureDatasets (Local)"]
  class CROWNBuildCombined["CROWNBuildCombined (Local)"]
  class CROWNBuild["CROWNBuild (Local)"]
  class BuildCROWNLib["BuildCROWNLib (Local)"]

  %% CROWN Friend Production Tasks
  class ProduceFriends["ProduceFriends (Local)"]
  class CROWNFriends["CROWNFriends (Workflow)"]
  class CROWNBuildFriend["CROWNBuildFriend (Local)"]
  class QuantitiesMap["QuantitiesMap (Local)"]

  %% CROWN Multi-Friend Production Tasks
  class ProduceMultiFriends["ProduceMultiFriends (Local)"]
  class CROWNMultiFriends["CROWNMultiFriends (Workflow)"]
  class CROWNBuildMultiFriend["CROWNBuildMultiFriend (Local)"]
  class FriendQuantitiesMap["FriendQuantitiesMap (Local)"]


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

  %% Styling for top-level entry points
  style ProduceSamples fill:#90EE90,stroke:#228B22,stroke-width:3px
  style ProduceFriends fill:#90EE90,stroke:#228B22,stroke-width:3px
  style ProduceMultiFriends fill:#90EE90,stroke:#228B22,stroke-width:3px

  %% Styling for workflow tasks
  style CROWNRun fill:#87CEEB,stroke:#4682B4,stroke-width:2px
  style CROWNFriends fill:#87CEEB,stroke:#4682B4,stroke-width:2px
  style CROWNMultiFriends fill:#87CEEB,stroke:#4682B4,stroke-width:2px
```

## Task Classification

### Top-Level Tasks (Entry Points) — Green boxes
Entry points that have no incoming dependencies. Users call these to start workflows:
- **ProduceSamples**: Triggers ntuple production for a list of samples
- **ProduceFriends**: Triggers friend production for a list of samples
- **ProduceMultiFriends**: Triggers multi-friend production for a list of samples

All three are **Local** tasks (do not inherit from `HTCondorWorkflow`), meaning they execute on the submission machine and orchestrate remote workflow tasks.

### Workflow Tasks — Blue boxes
Tasks that inherit from `HTCondorWorkflow`, meaning they submit jobs to run on HTCondor cluster:
- **CROWNRun**: Executes CROWN ntuple production on remote cluster
- **CROWNFriends**: Executes CROWN friend production on remote cluster
- **CROWNMultiFriends**: Executes CROWN multi-friend production on remote cluster

### Local Tasks
All other tasks are Local (do not inherit from `HTCondorWorkflow`), meaning they execute on the submission machine:
- Build tasks (`CROWNBuild*`, `BuildCROWNLib`) which are responsible to build tar archives. Those are needed by the remote workflows to provide them with all the tools/files they need.
- Configuration tasks (`ConfigureDatasets`)
- Quantities map aggregation tasks (`QuantitiesMap`, `FriendQuantitiesMap`)
