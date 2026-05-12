# Processor Class Inheritance Hierarchy

This diagram shows the inheritance relationships (parent-child) between Python classes in `processor/`.
The top-most parent classes are from the `law` library.


```mermaid
---
title: KingMaker Class Inheritance
---
%% keep a title to enlarge the diagram
%%{init: {"flowchart": {"titleTopMargin": 400}} }%%
flowchart TD
  %% LAW Library Base Classes
  LawTask["law.Task"]
  LawLocalWorkflow["law.LocalWorkflow"]
  LawHTCondorWorkflow["law.htcondor.HTCondorWorkflow"]
  LawWrapperTask["law.task.base.WrapperTask"]

  %% Framework Base Classes
  Task["Task"]
  HTCondorWorkflow["HTCondorWorkflow"]
  KingmakerSandbox["KingmakerSandbox"]

  %% CROWN Base Classes
  ProduceBase["ProduceBase"]
  CROWNExecuteBase["CROWNExecuteBase"]
  CROWNBuildBase["CROWNBuildBase"]

  %% Unified Production Task
  ProduceNtuples["ProduceNtuples"]

  %% CROWN Ntuple Production Tasks
  CROWNRun["CROWNRun"]
  ConfigureDatasets["ConfigureDatasets"]
  CROWNBuildCombined["CROWNBuildCombined"]
  CROWNBuild["CROWNBuild"]
  BuildCROWNLib["BuildCROWNLib"]

  %% CROWN Friend Production Tasks
  CROWNFriend["CROWNFriend"]
  CROWNBuildFriend["CROWNBuildFriend"]
  QuantitiesMap["QuantitiesMap"]

  %% Connections and Arrows
  %% The more --- in the arrow, the longer the arrow gets. This is important for better visibility of the graph.
  LawTask --> Task

  LawHTCondorWorkflow ---> HTCondorWorkflow
  Task --> HTCondorWorkflow
  HTCondorWorkflow --> CROWNExecuteBase

  LawLocalWorkflow ----> CROWNExecuteBase
  LawLocalWorkflow -----> QuantitiesMap

  Task ----> QuantitiesMap

  Task ----> BuildCROWNLib
  Task ----> ConfigureDatasets
  Task ---> CROWNBuildBase
  Task ---> ProduceBase
  KingmakerSandbox --> CROWNBuildBase

  CROWNBuildBase --> CROWNBuildFriend
  CROWNBuildBase --> CROWNBuild
  CROWNBuildBase --> CROWNBuildCombined

  ProduceBase --> ProduceNtuples

  CROWNExecuteBase --> CROWNRun
  CROWNExecuteBase --> CROWNFriend

  LawWrapperTask ----> ProduceBase

  %% Add Links to the classes
  click LawTask https://github.com/riga/law/blob/master/law/task/base.py "https://github.com/riga/law/blob/master/law/task/base.py"
  click LawLocalWorkflow https://law.readthedocs.io/en/latest/api/workflow/local.html "https://law.readthedocs.io/en/latest/api/workflow/local.html"
  click LawHTCondorWorkflow https://law.readthedocs.io/en/latest/contrib/htcondor.html "https://law.readthedocs.io/en/latest/contrib/htcondor.html"
  
  click Task https://github.com/KIT-CMS/KingMaker/blob/main/processor/framework.py "https://github.com/KIT-CMS/KingMaker/blob/main/processor/framework.py"
  click HTCondorWorkflow https://github.com/KIT-CMS/KingMaker/blob/main/processor/framework.py "https://github.com/KIT-CMS/KingMaker/blob/main/processor/framework.py"
  click KingmakerSandbox https://github.com/KIT-CMS/KingMaker/blob/main/processor/framework.py "https://github.com/KIT-CMS/KingMaker/blob/main/processor/framework.py"
  
  click ProduceBase https://github.com/KIT-CMS/KingMaker/blob/main/processor/tasks/CROWNBase.py "https://github.com/KIT-CMS/KingMaker/blob/main/processor/tasks/CROWNBase.py"
  click CROWNExecuteBase https://github.com/KIT-CMS/KingMaker/blob/main/processor/tasks/CROWNBase.py "https://github.com/KIT-CMS/KingMaker/blob/main/processor/tasks/CROWNBase.py"
  click CROWNBuildBase https://github.com/KIT-CMS/KingMaker/blob/main/processor/tasks/CROWNBase.py "https://github.com/KIT-CMS/KingMaker/blob/main/processor/tasks/CROWNBase.py"
  
  click ProduceNtuples https://github.com/KIT-CMS/KingMaker/blob/main/processor/tasks/ProduceNtuples.py "https://github.com/KIT-CMS/KingMaker/blob/main/processor/tasks/ProduceNtuples.py"
  click CROWNRun https://github.com/KIT-CMS/KingMaker/blob/main/processor/tasks/CROWNMain.py "https://github.com/KIT-CMS/KingMaker/blob/main/processor/tasks/CROWNMain.py"
  click ConfigureDatasets https://github.com/KIT-CMS/KingMaker/blob/main/processor/tasks/CROWNMain.py "https://github.com/KIT-CMS/KingMaker/blob/main/processor/tasks/CROWNMain.py"
  click CROWNBuildCombined https://github.com/KIT-CMS/KingMaker/blob/main/processor/tasks/CROWNMain.py "https://github.com/KIT-CMS/KingMaker/blob/main/processor/tasks/CROWNMain.py"
  click CROWNBuild https://github.com/KIT-CMS/KingMaker/blob/main/processor/tasks/CROWNMain.py "https://github.com/KIT-CMS/KingMaker/blob/main/processor/tasks/CROWNMain.py"
  click BuildCROWNLib https://github.com/KIT-CMS/KingMaker/blob/main/processor/tasks/CROWNMain.py "https://github.com/KIT-CMS/KingMaker/blob/main/processor/tasks/CROWNMain.py"
  
  click CROWNFriend https://github.com/KIT-CMS/KingMaker/blob/main/processor/tasks/CROWNFriend.py "https://github.com/KIT-CMS/KingMaker/blob/main/processor/tasks/CROWNFriend.py"
  click CROWNBuildFriend https://github.com/KIT-CMS/KingMaker/blob/main/processor/tasks/CROWNFriend.py "https://github.com/KIT-CMS/KingMaker/blob/main/processor/tasks/CROWNFriend.py"
  click QuantitiesMap https://github.com/KIT-CMS/KingMaker/blob/main/processor/tasks/CROWNFriend.py "https://github.com/KIT-CMS/KingMaker/blob/main/processor/tasks/CROWNFriend.py"
```

## Task Classification

### Top-Level Task (Entry Point) — Green box
Entry point that has no incoming dependencies. Users call this to start workflows:
- **ProduceNtuples**: Unified task that can trigger either ntuple production or friend production based on the `friend_config` parameter. Inherits from `ProduceBase` (WrapperTask).

This is a **Local** task (does not inherit from `HTCondorWorkflow`), meaning it executes on the submission machine and orchestrates remote workflow tasks.

### Workflow Tasks — Blue boxes
Tasks that inherit from `HTCondorWorkflow` (and `law.LocalWorkflow`), meaning they submit jobs to run on HTCondor cluster:
- **CROWNRun**: Executes CROWN ntuple production on remote cluster
- **CROWNFriend**: Executes CROWN friend production on remote cluster, handles friend dependencies through `friend_mapping`

### Local Tasks
All other tasks are Local (do not inherit from `HTCondorWorkflow`), meaning they execute on the submission machine:
- **Build tasks** (`CROWNBuild`, `CROWNBuildCombined`, `CROWNBuildFriend`, `BuildCROWNLib`) which are responsible for building tar archives. These are needed by the remote workflows to provide them with all the tools/files they need. Inherit from `CROWNBuildBase` and `KingmakerSandbox`.
- **Configuration tasks** (`ConfigureDatasets`) - loads dataset information from database
- **Quantities map extraction** (`QuantitiesMap`) - extracts quantities map from ROOT files after CROWN execution
```
