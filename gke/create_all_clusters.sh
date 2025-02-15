#!/bin/bash
# Copyright 2020 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

set -e

# Setup cluster in primary region
PRIMARY_REGION=$(yq eval '.region.primary' config.yaml)
./create_cluster.sh $PRIMARY_REGION

# Setup cluster in other regions
len=$(yq eval '.region.others | length' config.yaml)
for index in $(seq 0 $(($len-1)));
do
  export index=$index
  REGION=$(yq eval '.region.others[env(index)]' config.yaml)
  ./create_cluster.sh $REGION
done