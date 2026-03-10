#!/bin/bash

CURRENT_YEAR=$(date +%Y)
VENV_PATH="/venv"

docker run --rm -u root --entrypoint "/bin/bash" 52north/pygeoapi-k8s-manager:latest -c \
  "echo \"[\$(date -Is --utc)] 📥 Installing cyclonedx-bom...\" >&2 && \
   ${VENV_PATH}/bin/pip install --no-cache-dir cyclonedx-bom > /dev/null 2>&1 && \
   echo \"[\$(date -Is --utc)] 📦 Generating raw SBOM...\" >&2 && \
   ${VENV_PATH}/bin/python3 -m cyclonedx_py environment --output-format json --output-file /tmp/bom.json >&2 && \
   cat /tmp/bom.json" > cyclonedx_sbom_raw.json

echo "[$(date -Is --utc)] 🧹 Cleaning up and deduplicating SBOM (keeping highest versions)..."
jq '.components |= (
      map(select(.name != "pygeoapi-k8s-manager" and .name != "cyclonedx-bom" and .name != "cyclonedx-python-lib")) |
      group_by(.name | ascii_downcase) |
      map(max_by(.version | split(".") | map(tonumber? // 0))) |
      sort_by(.name | ascii_downcase)
    )' cyclonedx_sbom_raw.json > sbom.json

rm cyclonedx_sbom_raw.json

echo "[$(date -Is --utc)] 📝 Creating NOTICE file with header..."
cat << EOF > NOTICE
Copyright (C) 2025 - ${CURRENT_YEAR} 52°North Spatial Information Research GmbH

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

   http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

------------------------------------------------------------------------

This project includes the following dependencies:

EOF

echo "[$(date -Is --utc)] 🔗 Appending dependencies to NOTICE file..."
cat sbom.json | jq -r '
  ["Name", "Version", "License"],
  (.components | sort_by(.name | ascii_downcase) | .[] | [
    .name,
    .version,
    (if .licenses then
       (.licenses[0].license.id // .licenses[0].license.name // .licenses[0].expression // "Unknown") | sub("^License :: OSI Approved :: "; "")
     else "Unknown" end)
  ]) | @tsv' | column -t -s $'\t' >> NOTICE
rm sbom.json
echo "[$(date -Is --utc)] ✅ Done! 'sbom.json' and 'NOTICE' have been successfully created and formatted."
