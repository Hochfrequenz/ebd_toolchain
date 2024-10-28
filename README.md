# EBD Toolchain

![Unittests status badge](https://github.com/Hochfrequenz/ebd_toolchain/workflows/Unittests/badge.svg)
![Coverage status badge](https://github.com/Hochfrequenz/ebd_toolchain/workflows/Coverage/badge.svg)
![Linting status badge](https://github.com/Hochfrequenz/ebd_toolchain/workflows/Linting/badge.svg)
![Black status badge](https://github.com/Hochfrequenz/ebd_toolchain/workflows/Formatting/badge.svg)

🇩🇪 Dieses Repository enthält ein Python-Script, welches die beiden Python-Pakete [ebdamame](https://github.com/Hochfrequenz/ebdamame) 🫛 und [rebdhuhn](https://github.com/Hochfrequenz/rebdhuhn) 🐓 kombiniert, um aus .docx-Dateien maschinenlesbare Tabellen zur Modellierung von [edi@energy](https://www.edi-energy.de) Entscheidungsbäumen (EBD) zu extrahieren und anschließend in Form [echter Graphen](https://github.com/Hochfrequenz/machine-readable_entscheidungsbaumdiagramme/) zu visualisieren.
Diese Entscheidungsbäume sind Teil eines regulatorischen Regelwerks für die deutsche Energiewirtschaft und kommen in der Eingangsprüfung der Marktkommunikation zum Einsatz.

🇺🇸 This repository provides a Python script combining the libraries [ebdamame](https://github.com/Hochfrequenz/ebdamame) and [rebdhuhn](https://github.com/Hochfrequenz/rebdhuhn) in order to render [edi@energy](https://www.edi-energy.de) _Entscheidungsbaumdiagramme_ (EBD) as both machine-readable tables as well as corresponding graphs in `.svg` and `.uml` format.

## How to use EBD Toolchain
You can either run the toolchain via Python (requires Docker AND Python to be installed on your machine).
Or you can run the entire toolchain in a docker container (requires only Docker).

### Option A: Via Python + Kroki in a Docker Container

#### Install both libraries from PiPy:
```bash
pip install -r requirements.txt
```
Further, make sure to have a local instance of [kroki](https://kroki.io) up and running via docker (localhost:8125) as described in the [rebdhuhn](https://github.com/Hochfrequenz/rebdhuhn) readme.
Run the `docker-desktop` app on your local maschine and start the local kroki container via
```bash
docker-compose up -d
```
#### Execute the EBD toolchain script:

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

### Option B: Docker only (no Python required)
In this repository:
1. create an `.env` file with a structure similar to [`env.example`](env.example).
2. set the environment variables to meaningful values.
3. Create a `docker-compose.yml` with the following content:
```yaml
services:
  kroki:
    image: yuzutech/kroki:0.24.1
    ports:
      - "8125:8000"  # Expose Kroki on port 8125 for rendering diagrams
      # we hardcode 8125 because of https://github.com/Hochfrequenz/rebdhuhn/issues/205
    healthcheck:
      test: [ "CMD", "curl", "-f", "http://localhost:8000/health" ]
      interval: 10s
      timeout: 5s
      retries: 3

  scrape-and-plot:
    image: ghcr.io/hochfrequenz/ebd_toolchain:latest
    # If you run into 'manifest unknown' during docker pull, try replacing `:latest` with `:v1.2.3`.
    # where v1.2.3 is the latest version of the GHCR image, which can be found here:
    # https://github.com/Hochfrequenz/ebd_toolchain/pkgs/container/ebd_toolchain
    depends_on:
      kroki:
        condition: service_healthy
    volumes:
      - ${EBD_DOCX_FILE}:/container/ebd.docx
      - ${OUTPUT_DIR}:/container/output
    network_mode: host
```
4. Login to GitHub Container Registry (GHCR); Use a [Personal Access Token](https://github.com/settings/tokens/new) (PAT) to login that has access to this repository and at least `read:packages` scope
```bash
docker login ghcr.io -u YOUR_GITHUB_USERNAME
```
5. then run:
```bash
docker compose up --abort-on-container-exit
```

You can find a [Github Action with exactly this setup](https://github.com/Hochfrequenz/edi_energy_mirror/blob/master/.github/workflows/ebdamame_rebdhuhn.yml) our edi_energy_mirror where it's used to automatically scrape the latest `.docx` files and pushes the results to [machine-readable_entscheidungsbaumdiagramme](https://github.com/Hochfrequenz/machine-readable_entscheidungsbaumdiagramme/) which is then used by our frontend  [`entscheidungbaumdiagramm`](https://github.com/Hochfrequenz/entscheidungsbaumdiagramm/).

## How to use this Repository on Your Machine (for development)

Please follow the instructions in our
[Python Template Repository](https://github.com/Hochfrequenz/python_template_repository#how-to-use-this-repository-on-your-machine).
And for further information, see the [Tox Repository](https://github.com/tox-dev/tox).

## Contribute

You are very welcome to contribute to this template repository by opening a pull request against the main branch.

## Related Tools and Context

This repository is part of the [Hochfrequenz Libraries and Tools for a truly digitized market communication](https://github.com/Hochfrequenz/digital_market_communication/).
