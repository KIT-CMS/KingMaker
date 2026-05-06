# Processor Task Dependencies

This diagram shows only the task dependencies (requires/workflow_requires) between Python classes in `processor/`.
These are the actual execution flow dependencies that determine task ordering.

```mermaid
flowchart BT
  %% Legend nodes
  L2["Workflow task inheriting from <code>HTCondorWorkflow</code> (executes on remote cluster)"]
  L3["Local task (does not inherit from <code>HTCondorWorkflow</code>)"]
  L1["Task which is executed by the user. Spawns workflows but is not a workflow itself."]
  L4["────▶ requires()"]
  L5["· · · ▶ workflow_requires()"]

  %% Legend styling
  subgraph LEGEND["Legend"]
    L1
    L2
    L3
    L4
    L5
  end
  style LEGEND stroke:#999,stroke-width:2px,text-decoration: underline
  style L1 fill:#90EE90,stroke:#228B22,stroke-width:3px,color:#000,font-size:14px
  style L2 stroke:#4682B4,stroke-width:2px,font-size:14px
  style L3 stroke:#228B22,stroke-width:2px,font-size:14px
  style L4 fill:none,stroke:none
  style L5 fill:none,stroke:none
```
```mermaid
flowchart TD
  %% CROWN Ntuple Production Tasks
  ProduceSamples["ProduceSamples"]
  CROWNRun["CROWNRun"]
  ConfigureDatasets["ConfigureDatasets"]
  CROWNBuildCombined["CROWNBuildCombined"]
  CROWNBuild["CROWNBuild"]
  BuildCROWNLib["BuildCROWNLib"]

  %% CROWN Friend Production Tasks
  ProduceFriends["ProduceFriends"]
  CROWNFriends["CROWNFriends"]
  CROWNBuildFriend["CROWNBuildFriend"]
  QuantitiesMap["QuantitiesMap"]

  %% CROWN Multi-Friend Production Tasks
  ProduceMultiFriends["ProduceMultiFriends"]
  CROWNMultiFriends["CROWNMultiFriends"]
  CROWNBuildMultiFriend["CROWNBuildMultiFriend"]
  FriendQuantitiesMap["FriendQuantitiesMap"]

  %% === TASK DEPENDENCIES (requires/workflow_requires) ===

  %% CROWN Ntuple Production dependencies
  CROWNRun -.->|workflow_requires| ConfigureDatasets
  CROWNRun -.->|workflow_requires| CROWNBuild
  CROWNBuildCombined -->|requires| BuildCROWNLib
  CROWNBuild -->|requires| CROWNBuildCombined
  ProduceSamples -------->|requires| CROWNRun

  %% CROWN Friend Production dependencies
  CROWNFriends -.->|workflow_requires| CROWNRun
  CROWNFriends -.->|workflow_requires| CROWNBuildFriend
  CROWNBuildFriend -->|requires| QuantitiesMap
  CROWNBuildFriend -->|requires| BuildCROWNLib
  ProduceFriends ----->|requires| CROWNFriends

  %% CROWN Multi-Friend Production dependencies
  CROWNMultiFriends -.->|workflow_requires| CROWNRun
  CROWNMultiFriends -.->|workflow_requires| CROWNBuildMultiFriend
  CROWNMultiFriends -.->|workflow_requires| CROWNFriends
  CROWNBuildMultiFriend -->|requires| BuildCROWNLib
  CROWNBuildMultiFriend -->|requires| FriendQuantitiesMap
  FriendQuantitiesMap -.->|workflow_requires| CROWNRun
  FriendQuantitiesMap -.->|workflow_requires| CROWNFriends
  ProduceMultiFriends -->|requires| CROWNMultiFriends
  QuantitiesMap -.->|workflow_requires| CROWNRun

  %% Styling for top-level entry points
  style ProduceSamples fill:#90EE90,stroke:#228B22,stroke-width:3px,color:#000
  style ProduceFriends fill:#90EE90,stroke:#228B22,stroke-width:3px,color:#000
  style ProduceMultiFriends fill:#90EE90,stroke:#228B22,stroke-width:3px,color:#000

  %% Styling for workflow tasks
  style CROWNRun stroke:#4682B4,stroke-width:2px
  style CROWNFriends stroke:#4682B4,stroke-width:2px
  style CROWNMultiFriends stroke:#4682B4,stroke-width:2px

  %% Styling for local tasks with green border
  style ConfigureDatasets stroke:#228B22,stroke-width:2px
  style CROWNBuildCombined stroke:#228B22,stroke-width:2px
  style CROWNBuild stroke:#228B22,stroke-width:2px
  style BuildCROWNLib stroke:#228B22,stroke-width:2px
  style CROWNBuildFriend stroke:#228B22,stroke-width:2px
  style QuantitiesMap stroke:#228B22,stroke-width:2px
  style CROWNBuildMultiFriend stroke:#228B22,stroke-width:2px
  style FriendQuantitiesMap stroke:#228B22,stroke-width:2px
```

## Reduced Task Flows

### CROWN Ntuple Production

<details>
<summary>Click to expand CROWN Ntuple Production flow details</summary>

```mermaid
flowchart TD
  %% CROWN Ntuple Production Tasks
  ProduceSamples["ProduceSamples"]
  CROWNRun["CROWNRun"]
  ConfigureDatasets["ConfigureDatasets"]
  CROWNBuildCombined["CROWNBuildCombined"]
  CROWNBuild["CROWNBuild"]
  BuildCROWNLib["BuildCROWNLib"]

  %% CROWN Ntuple Production dependencies
  CROWNRun -.->|workflow_requires| ConfigureDatasets
  CROWNRun -.->|workflow_requires| CROWNBuild
  CROWNBuildCombined -->|requires| BuildCROWNLib
  CROWNBuild -->|requires| CROWNBuildCombined
  ProduceSamples -->|requires| CROWNRun

  %% Styling for top-level entry points
  style ProduceSamples fill:#90EE90,stroke:#228B22,stroke-width:3px,color:#000

  %% Styling for workflow tasks
  style CROWNRun stroke:#4682B4,stroke-width:2px

  %% Styling for local tasks with green border
  style ConfigureDatasets stroke:#228B22,stroke-width:2px
  style CROWNBuildCombined stroke:#228B22,stroke-width:2px
  style CROWNBuild stroke:#228B22,stroke-width:2px
  style BuildCROWNLib stroke:#228B22,stroke-width:2px

```

</details>

### CROWN Friend Production

<details>
<summary>Click to expand CROWN Friend Production flow details</summary>


```mermaid
flowchart TD
  %% CROWN Ntuple Production Tasks
  CROWNRun["CROWNRun"]
  ConfigureDatasets["ConfigureDatasets"]
  CROWNBuildCombined["CROWNBuildCombined"]
  CROWNBuild["CROWNBuild"]
  BuildCROWNLib["BuildCROWNLib"]

  %% CROWN Friend Production Tasks
  ProduceFriends["ProduceFriends"]
  CROWNFriends["CROWNFriends"]
  CROWNBuildFriend["CROWNBuildFriend"]
  QuantitiesMap["QuantitiesMap"]

  %% CROWN Multi-Friend Production dependencies
  QuantitiesMap -.->|workflow_requires| CROWNRun

  %% CROWN Ntuple Production dependencies
  CROWNRun -.->|workflow_requires| ConfigureDatasets
  CROWNRun -.->|workflow_requires| CROWNBuild
  CROWNBuildCombined -->|requires| BuildCROWNLib
  CROWNBuild -->|requires| CROWNBuildCombined

  %% CROWN Friend Production dependencies
  CROWNFriends -.->|workflow_requires| CROWNRun
  CROWNFriends -.->|workflow_requires| CROWNBuildFriend
  CROWNBuildFriend -->|requires| QuantitiesMap
  CROWNBuildFriend -->|requires| BuildCROWNLib
  ProduceFriends -->|requires| CROWNFriends

  %% Styling for top-level entry points
  style ProduceFriends fill:#90EE90,stroke:#228B22,stroke-width:3px,color:#000

  %% Styling for workflow tasks
  style CROWNRun stroke:#4682B4,stroke-width:2px
  style CROWNFriends stroke:#4682B4,stroke-width:2px

  %% Styling for local tasks with green border
  style ConfigureDatasets stroke:#228B22,stroke-width:2px
  style CROWNBuildCombined stroke:#228B22,stroke-width:2px
  style CROWNBuild stroke:#228B22,stroke-width:2px
  style BuildCROWNLib stroke:#228B22,stroke-width:2px
  style CROWNBuildFriend stroke:#228B22,stroke-width:2px
  style QuantitiesMap stroke:#228B22,stroke-width:2px
```

</details>

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
