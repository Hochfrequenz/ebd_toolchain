# EBD Toolchain

![Unittests status badge](https://github.com/Hochfrequenz/ebd_toolchain/workflows/Unittests/badge.svg)
![Coverage status badge](https://github.com/Hochfrequenz/ebd_toolchain/workflows/Coverage/badge.svg)
![Linting status badge](https://github.com/Hochfrequenz/ebd_toolchain/workflows/Linting/badge.svg)
![Black status badge](https://github.com/Hochfrequenz/ebd_toolchain/workflows/Formatting/badge.svg)

🇩🇪 Dieses Repository enthält ein Python-Script, welches die beiden Python-Pakete [ebdamame](https://github.com/Hochfrequenz/ebdamame) 🫛 und [rebdhuhn](https://github.com/Hochfrequenz/rebdhuhn) 🐓 kombiniert, um aus .docx-Dateien maschinenlesbare Tabellen zur Modellierung von [edi@energy](https://www.edi-energy.de) Entscheidungsbäumen (EBD) zu extrahieren und anschließend in Form [echter Graphen](https://github.com/Hochfrequenz/machine-readable_entscheidungsbaumdiagramme/) zu visualisieren.
Diese Entscheidungsbäume sind Teil eines regulatorischen Regelwerks für die deutsche Energiewirtschaft und kommen in der Eingangsprüfung der Marktkommunikation zum Einsatz.

🇺🇸 This repository provides a Python script combining the libraries [ebdamame](https://github.com/Hochfrequenz/ebdamame) and [rebdhuhn](https://github.com/Hochfrequenz/rebdhuhn) in order to render [edi@energy](https://www.edi-energy.de) _Entscheidungsbaumdiagramme_ (EBD) as both machine-readable tables as well as corresponding graphs in `.svg` and `.uml` format.

## How to use EBD Toolchain

### Install both libraries from PiPy:
```bash
pip install ebdamame
```
```bash
pip install rebdhuhn
```
Further, make sure to have a local instance of [kroki](https://kroki.io) up and running via docker (localhost:8126). Add the required `.env` file to the repository root by opening a new terminal session, changing the directory to
```bash
cd path\to\rebdhuhn\repository\root
```
and executing the `create_env_file.py` script via
```bash
python create_env_file.py
```
Run the `docker-desktop` app on your local maschine and host the local kroki instance on PORT `8126` via
```bash
docker-compose up -d
```
### Execute the EBD toolchain script:
 
Run `main.py` using your IDE or inside a terminal session via
```bash
python main.py
```
Keep following the on-screen prompts given by the terminal and provide

- the path of the directory containing the `.docx` edi@energy EBD file
- the path to the output directory
- the desired data formats `.json`, `.dot`, `.svg` or `.puml`.

Alternatively, the script can simply be executed using the single command

```bash
main.py -i <path to .doxc location> -o <output directory> -t json -t dot -t svg -t puml
```
where `-i`, `-o` and `-t` denote the input directory path, the output directory path and the supported data format, respectively.

## How to use this Repository on Your Machine (for development)

Please follow the instructions in our
[Python Template Repository](https://github.com/Hochfrequenz/python_template_repository#how-to-use-this-repository-on-your-machine).
And for further information, see the [Tox Repository](https://github.com/tox-dev/tox).

## Contribute

You are very welcome to contribute to this template repository by opening a pull request against the main branch.

## Related Tools and Context

This repository is part of the [Hochfrequenz Libraries and Tools for a truly digitized market communication](https://github.com/Hochfrequenz/digital_market_communication/).
