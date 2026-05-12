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
  %% CROWN Production Tasks (Unified)
  ProduceNtuples["ProduceNtuples"]
  CROWNRun["CROWNRun"]
  CROWNFriend["CROWNFriend"]
  ConfigureDatasets["ConfigureDatasets"]
  CROWNBuildCombined["CROWNBuildCombined"]
  CROWNBuild["CROWNBuild"]
  BuildCROWNLib["BuildCROWNLib"]
  CROWNBuildFriend["CROWNBuildFriend"]
  QuantitiesMap["QuantitiesMap"]

  %% === TASK DEPENDENCIES (requires/workflow_requires) ===

  %% CROWN Ntuple Production dependencies
  CROWNRun -.->|workflow_requires| ConfigureDatasets
  CROWNRun -.->|workflow_requires| CROWNBuild
  CROWNBuildCombined -->|requires| BuildCROWNLib
  CROWNBuild -->|requires| CROWNBuildCombined
  ProduceNtuples -->|requires| CROWNRun
  ProduceNtuples -->|requires| CROWNFriend

  %% CROWN Friend Production dependencies
  CROWNFriend -.->|workflow_requires| CROWNRun
  CROWNFriend -.->|workflow_requires| CROWNBuildFriend
  CROWNFriend -.->|workflow_requires| CROWNFriend
  CROWNBuildFriend -->|requires| QuantitiesMap
  CROWNBuildFriend -->|requires| BuildCROWNLib
  QuantitiesMap -->|requires| CROWNRun
  QuantitiesMap -->|requires| CROWNFriend

  %% Styling for top-level entry points
  style ProduceNtuples fill:#90EE90,stroke:#228B22,stroke-width:3px,color:#000

  %% Styling for workflow tasks
  style CROWNRun stroke:#4682B4,stroke-width:2px
  style CROWNFriend stroke:#4682B4,stroke-width:2px

  %% Styling for local tasks with green border
  style ConfigureDatasets stroke:#228B22,stroke-width:2px
  style CROWNBuildCombined stroke:#228B22,stroke-width:2px
  style CROWNBuild stroke:#228B22,stroke-width:2px
  style BuildCROWNLib stroke:#228B22,stroke-width:2px
  style CROWNBuildFriend stroke:#228B22,stroke-width:2px
  style QuantitiesMap stroke:#228B22,stroke-width:2px
```

## Reduced Task Flows

### CROWN Ntuple Production

<details>
<summary>Click to expand CROWN Ntuple Production flow details</summary>

```mermaid
flowchart TD
  %% CROWN Ntuple Production Tasks
  ProduceNtuples["ProduceNtuples"]
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
  ProduceNtuples -->|requires| CROWNRun

  %% Styling for top-level entry points
  style ProduceNtuples fill:#90EE90,stroke:#228B22,stroke-width:3px,color:#000

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
  ProduceNtuples["ProduceNtuples"]
  CROWNFriend["CROWNFriend"]
  CROWNBuildFriend["CROWNBuildFriend"]
  QuantitiesMap["QuantitiesMap"]

  %% Quantities map dependencies
  QuantitiesMap -->|requires| CROWNRun
  QuantitiesMap -->|requires| CROWNFriend

  %% CROWN Ntuple Production dependencies
  CROWNRun -.->|workflow_requires| ConfigureDatasets
  CROWNRun -.->|workflow_requires| CROWNBuild
  CROWNBuildCombined -->|requires| BuildCROWNLib
  CROWNBuild -->|requires| CROWNBuildCombined

  %% CROWN Friend Production dependencies
  CROWNFriend -.->|workflow_requires| CROWNRun
  CROWNFriend -.->|workflow_requires| CROWNBuildFriend
  CROWNBuildFriend -->|requires| QuantitiesMap
  CROWNBuildFriend -->|requires| BuildCROWNLib
  ProduceNtuples -->|requires| CROWNFriend

  %% Styling for top-level entry points
  style ProduceNtuples fill:#90EE90,stroke:#228B22,stroke-width:3px,color:#000

  %% Styling for workflow tasks
  style CROWNRun stroke:#4682B4,stroke-width:2px
  style CROWNFriend stroke:#4682B4,stroke-width:2px

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

### Top-Level Task (Entry Point) — Green box
Entry point that has no incoming dependencies. Users call this to start workflows:
- **ProduceNtuples**: Unified task that triggers either ntuple production (via `CROWNRun`) or friend production (via `CROWNFriend`) based on the `friend_config` parameter. When `friend_config=""` (empty, default), it triggers ntuple production. When `friend_config` is set to a specific configuration, it triggers friend production. Can handle multi-friend scenarios through the `friend_mapping` parameter.

**Local** task (does not inherit from `HTCondorWorkflow`), meaning it executes on the submission machine and orchestrates remote workflow tasks.

### Workflow Tasks — Blue boxes
Tasks that inherit from `HTCondorWorkflow`, meaning they submit jobs to run on HTCondor cluster:
- **CROWNRun**: Executes CROWN ntuple production on remote cluster
- **CROWNFriend**: Executes CROWN friend production on remote cluster, can handle friend dependencies through `friend_mapping`

### Local Tasks
All other tasks are Local (do not inherit from `HTCondorWorkflow`), meaning they execute on the submission machine:
- Build tasks (`CROWNBuild*`, `BuildCROWNLib`) which are responsible for building tar archives. Those are needed by the remote workflows to provide them with all the tools/files they need.
- Configuration tasks (`ConfigureDatasets`)
- Quantities map extraction tasks (`QuantitiesMap`)
