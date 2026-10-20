# Aktuelles Problem vor der mt-Produktion

Stand: 13. Oktober 2026. Arbeitsverzeichnis: `/work/skaiser/Embedding/Kingmaker_tauID/KingMaker`.

## Zusammenfassung

Die mm-Produktion ist abgeschlossen. Für mt sind Sampleliste und Datenbank vorbereitet. Der aktuelle Quellcodestand enthält jedoch eine inkompatible Tau-ID-Schnittstelle zwischen TauAnalysis und CROWN. Betroffen ist der Build der mt-MC-Executables für 2024.

Es handelt sich um einen anhand des Quellcodes festgestellten Build-Blocker. Ein neuer mt-Build wurde bei dieser Prüfung nicht ausgeführt. Die erfolgreiche mm-Produktion ist kein Nachweis für die Kompatibilität dieses mt-spezifischen Aufrufs.

## Welche Versionen liegen aktuell vor?

Die folgenden Ordner sind getrennte Git-Repositories. Ein Branchwechsel in einem Repository aktualisiert die anderen nicht automatisch.

| Repository | Ordner relativ zu KingMaker | Branch | Aktueller Commit |
|---|---|---|---|
| KingMaker | `.` | `main` | `3258776` |
| CROWN | `CROWN` | `main` | `eacc01c32199518cef7f5584ad355f3135b97ec3` |
| TauAnalysis-CROWN | `CROWN/analysis_configurations/tau` | `SFs_tauID_dev_v15_CW_SK` | `7ace41b03fb4f4a9a7d615ee0065f5c3b5f8aae4` |
| Sample-Datenbank | `sample_database` | `main` | `cec33f923874f2e28c988b19cf996a0a08c10cbf` |

CROWN und TauAnalysis haben zum Prüfzeitpunkt keine uncommitteten Dateiänderungen. Die Markierungen `M CROWN` und `M sample_database` im übergeordneten KingMaker beziehen sich auf abweichende Submodule-Commits.

Der lokale Datenbankbranch liegt einen Commit vor dem zuletzt gespeicherten `origin/main` (`f56dd8d3`). Der aktuelle GitHub-Stand wurde nicht neu abgefragt; daraus folgt keine gesicherte Aussage darüber, ob der Commit von einem anderen Rechner bereits veröffentlicht wurde.

## Der konkrete Fehler: drei unterschiedliche Funktionsschnittstellen

Die betroffene Funktion heißt:

~~~cpp
physicsobject::tau::scalefactor::experimental::Id_vsJet(...)
~~~

Aufruf, Deklaration und Definition haben aktuell unterschiedliche Parameterlisten:

| Stelle | Datei und Zeilen im geprüften Stand | Anzahl Argumente bzw. Parameter | Unterschied |
|---|---|---:|---|
| TauAnalysis-Aufruf | [scalefactors.py](CROWN/analysis_configurations/tau/producers/scalefactors.py), Zeilen 515–529 | 12 | Übergibt weder `era` noch einen VSmu-Arbeitspunkt |
| CROWN-Deklaration | [taus.hxx](CROWN/include/taus.hxx), Zeilen 355–362 | 14 | Erwartet zusätzlich `era` und `id_vsmu_wp` |
| CROWN-Definition | [taus.cxx](CROWN/src/taus.cxx), Zeilen 3151–3158 | 13 | Erwartet `id_vsmu_wp`, enthält aber keinen `era`-Parameter |

Bei der Zählung des Producer-Aufrufs ist berücksichtigt, dass `{input}` zu drei Argumenten expandiert: Tau-pT, Zerfallsmodus und Gen-Matching.

Daraus ergeben sich zwei Probleme:

1. Der generierte Aufruf aus TauAnalysis passt nicht zur aktuellen CROWN-Deklaration. Beim Kompilieren des mt-MC-Codes ist deshalb ein Fehler wegen einer nicht passenden Funktionssignatur zu erwarten.
2. Auch CROWN-Deklaration und CROWN-Definition stimmen untereinander nicht überein. Nur zusätzliche Argumente im TauAnalysis-Producer einzufügen würde diesen Widerspruch nicht lösen.

Ein Branchname wie `main` gewährleistet keine Kompatibilität mit einem separat ausgecheckten Analysebranch.

## Warum war mm trotzdem erfolgreich?

Die verwendete [Analysekonfiguration](CROWN/analysis_configurations/tau/config_run3_v15_tau_embedding_tauid_es_sf.py) wählt ab dem Jahr 2024 die Gruppe `TauID_SF_Experimental` aus, siehe Zeilen 55–63.

Diese Tau-ID-Gruppe wird in mt verwendet, siehe Zeile 892. Für `data`, `embedding` und `embedding_mc` wird sie durch eine Modifikationsregel wieder entfernt, siehe Zeile 927. Der konkrete Aufruf betrifft somit insbesondere mt-MC und wird in mm nicht benötigt.

Der Fehler hängt nicht von `--shifts all` ab: Auch ein nominaler mt-MC-Build benötigt die passende Schnittstelle.

## Was wurde in welchem Repository bearbeitet?

- **CROWN/main:** Die 2024C-Embedding-SF-Dateien unter `CROWN/data/embedding/` sind bereits enthalten. Beispiele sind die Commits `e3f4af9` und `35e487c`.
- **TauAnalysis, Branch SFs_tauID_dev_v15_CW_SK:** Hier liegen die eigentliche Tau-ID-/TauES-Config, die Embedding-Settings, Producer und Variationen. Relevante Implementierungscommits sind unter anderem `e60ec35` und `a6f5b6a`. Sie sind im lokal bekannten `origin/main` dieses Repositories nicht enthalten.
- **Sample-Datenbank/main:** Commit `cec33f92` aktualisiert die Embedding-Metadaten in `nanoAOD_v15/datasets.json`.
- **Lokale Samplelisten:** [samples_2024C_mm.txt](samples_2024C_mm.txt) und [samples_2024C_mt.txt](samples_2024C_mt.txt) werden durch die Gitignore-Regel `*.txt` ausgeschlossen. Sie gehören derzeit zu keinem Git-Commit.

## Mögliche Lösungen

### A: Auf die von KingMaker hinterlegte CROWN-Version wechseln

KingMaker hinterlegt für sein CROWN-Submodule diesen Commit:

~~~text
644f7f19f1a0f3d8755d7c9e17b786e0e5567bb2
~~~

Bei dieser lokal vorhandenen Revision passen die Deklaration und Definition von `experimental::Id_vsJet` zum vorhandenen TauAnalysis-Aufruf. Ein möglicher manueller Wechsel aus dem KingMaker-Verzeichnis wäre:

~~~bash
git -C CROWN -c submodule.recurse=false switch --detach \
  644f7f19f1a0f3d8755d7c9e17b786e0e5567bb2
~~~

Dieser Wechsel wurde nicht ausgeführt. Er würde CROWN im detached HEAD auschecken und den TauAnalysis-Branch nicht umstellen.

Die beiden eigenen SF-Dateien `data/embedding/muon_2024C.json.gz` und `data/embedding/embeddingselection_2024C.json.gz` sind bereits in dieser Revision enthalten und gegenüber `eacc01c` unverändert. Spätere CROWN-Änderungen, darunter Logger-Lock- und Performance-Korrekturen, wären bei diesem Wechsel dagegen nicht aktiv.

Geprüft wurde die Übereinstimmung der Funktionssignaturen. Ein vollständiger mt-Build und die Laufzeit mit den verwendeten Korrekturdateien wurden für diese Kombination noch nicht geprüft.

### B: CROWN/main und TauAnalysis gemeinsam korrigieren

Wenn CROWN auf dem aktuellen main-Stand bleiben soll, müssen drei Stellen abgestimmt werden:

1. Die Deklaration in `CROWN/include/taus.hxx`.
2. Die Definition in `CROWN/src/taus.cxx`.
3. Der Producer-Aufruf in `CROWN/analysis_configurations/tau/producers/scalefactors.py`.

Die Zielsignatur und der VSmu-Arbeitspunkt müssen zur verwendeten Tau-Korrekturdatei passen. Danach sind ein neuer Build und eine Laufzeitprüfung erforderlich. Die Tau-ID-Skalierungsfaktoren für MC lediglich zu entfernen wäre eine Änderung der Analyse und keine reine Schnittstellenkorrektur.

## Geprüfter Produktionsstand

Der vorhandene [ROOT-Prüfbericht für mm](check_mm_2024C_root.txt) meldet:

- 3.010 erwartete und geprüfte Dateien für 34 Samples.
- 3.010 Dateien mit lesbarer Struktur und `ntuple`-Baum.
- 706 Bäume mit null ausgewählten Ereignissen.
- 0 Fehler bei dieser Strukturprüfung.

Die Leerstände konzentrieren sich auf Prozesse mit geringer mm-Akzeptanz, insbesondere DY→ee und W→eν. In Muon-Daten, MuMuEmbedding und DY→μμ enthält der Bericht keine leeren Dateien. Es wurden Metadaten und Baumstruktur geprüft, nicht sämtliche gespeicherten Ereignisdaten vollständig gelesen.

Für mt ist die [Sampleliste](samples_2024C_mt.txt) vorbereitet:

- 34 Samples mit gültigen, befüllten Datenbankdateien.
- MuTauEmbedding statt MuMuEmbedding; 182 Eingabedateien im MuTauEmbedding-Sample.
- Bei zehn Eingabedateien pro Job insgesamt 2.992 erwartete ROOT-Ausgabedateien.
- Zum Prüfzeitpunkt keine lokalen mt-Produktionsverzeichnisse unter `data`, `build` oder `tarballs`; ein möglicher vorhandener Remote-Stand wurde nicht abgefragt.

## Nach Behebung der Schnittstelle

Für mt ist ein eigener Produktionstag nötig, beispielsweise `tauid_2024C_mt_all_v3`. Die Buildpfade enthalten den Produktionstag, aber keinen separaten Scope-Schlüssel. Der vorhandene mm-Tag würde deshalb die Wiederverwendung von mm-Buildartefakten riskieren.

Mit der aktuellen Speicher-Konfiguration lautet das erwartete Ziel für einen solchen mt-Tag:

~~~text
root://cmsdcache-kit-disk.gridka.de//store/user/skaiser/CROWN/ntuples/tauid_2024C_mt_all_v3/CROWNRun/2024/<nick>/mt/<nick>_<branch>.root
~~~

Diese Dokumentation hält Diagnose und mögliche nächste Schritte fest. Bei ihrer Erstellung wurden keine Quellcodedateien geändert, keine Git-Versionen umgestellt und keine Produktionsjobs gestartet.
