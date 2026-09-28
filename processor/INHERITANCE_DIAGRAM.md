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
  CROWNLocalBuildBase["CROWNLocalBuildBase"]

  %% Unified Production Task
  ProduceNtuples["ProduceNtuples"]

  %% CROWN Ntuple Production Tasks
  CROWNRun["CROWNRun"]
  ConfigureDatasets["ConfigureDatasets"]
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
  HTCondorWorkflow --> CROWNBuild
  HTCondorWorkflow --> CROWNBuildFriend

  LawLocalWorkflow ----> CROWNExecuteBase
  LawLocalWorkflow -----> CROWNBuild
  LawLocalWorkflow -----> CROWNBuildFriend

  Task ---> ProduceBase

  %% CROWNBuildBase is a plain mixin (params/helpers only, no Task/SandboxTask base
  %% of its own) so it composes with either execution model below.
  CROWNBuildBase --> CROWNBuild
  CROWNBuildBase --> CROWNBuildFriend
  CROWNBuildBase --> CROWNLocalBuildBase

  KingmakerSandbox --> CROWNLocalBuildBase
  Task --> CROWNLocalBuildBase
  CROWNLocalBuildBase --> BuildCROWNLib
  CROWNLocalBuildBase --> QuantitiesMap

  Task ----> ConfigureDatasets

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
  click CROWNLocalBuildBase https://github.com/KIT-CMS/KingMaker/blob/main/processor/tasks/CROWNBase.py "https://github.com/KIT-CMS/KingMaker/blob/main/processor/tasks/CROWNBase.py"
  
  click ProduceNtuples https://github.com/KIT-CMS/KingMaker/blob/main/processor/tasks/ProduceNtuples.py "https://github.com/KIT-CMS/KingMaker/blob/main/processor/tasks/ProduceNtuples.py"
  click CROWNRun https://github.com/KIT-CMS/KingMaker/blob/main/processor/tasks/CROWNMain.py "https://github.com/KIT-CMS/KingMaker/blob/main/processor/tasks/CROWNMain.py"
  click ConfigureDatasets https://github.com/KIT-CMS/KingMaker/blob/main/processor/tasks/CROWNMain.py "https://github.com/KIT-CMS/KingMaker/blob/main/processor/tasks/CROWNMain.py"
  click CROWNBuild https://github.com/KIT-CMS/KingMaker/blob/main/processor/tasks/CROWNMain.py "https://github.com/KIT-CMS/KingMaker/blob/main/processor/tasks/CROWNMain.py"
  click BuildCROWNLib https://github.com/KIT-CMS/KingMaker/blob/main/processor/tasks/CROWNMain.py "https://github.com/KIT-CMS/KingMaker/blob/main/processor/tasks/CROWNMain.py"
  
  click CROWNFriend https://github.com/KIT-CMS/KingMaker/blob/main/processor/tasks/CROWNFriend.py "https://github.com/KIT-CMS/KingMaker/blob/main/processor/tasks/CROWNFriend.py"
  click CROWNBuildFriend https://github.com/KIT-CMS/KingMaker/blob/main/processor/tasks/CROWNFriend.py "https://github.com/KIT-CMS/KingMaker/blob/main/processor/tasks/CROWNFriend.py"
  click QuantitiesMap https://github.com/KIT-CMS/KingMaker/blob/main/processor/tasks/CROWNFriend.py "https://github.com/KIT-CMS/KingMaker/blob/main/processor/tasks/CROWNFriend.py"
```
