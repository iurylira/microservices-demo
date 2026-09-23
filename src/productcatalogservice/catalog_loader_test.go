// Copyright 2024 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//      https://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

package main

import (
	"testing"

	pb "github.com/GoogleCloudPlatform/microservices-demo/src/productcatalogservice/genproto"
)

// assertLoadsLocalCatalog calls loadCatalog on an empty catalog and expects the
// 9 products of products.json (read from the package dir, the test cwd).
func assertLoadsLocalCatalog(t *testing.T) {
	t.Helper()
	var catalog pb.ListProductsResponse

	if err := loadCatalog(&catalog); err != nil {
		t.Fatalf("loadCatalog returned error: %v", err)
	}

	if got, want := len(catalog.Products), 9; got != want {
		t.Errorf("got %d products, want %d", got, want)
	}
	found := false
	for _, p := range catalog.Products {
		if p.Id == "OLJCESPC7Z" {
			found = true
			break
		}
	}
	if !found {
		t.Errorf("product OLJCESPC7Z not found in loaded catalog")
	}
}

// T-011: Given no ALLOYDB_* env, When loadCatalog runs, Then it loads products.json.
func TestLoadCatalog_Default_LoadsProductsJSON(t *testing.T) {
	t.Setenv("ALLOYDB_CLUSTER_NAME", "")

	assertLoadsLocalCatalog(t)
}

// T-012: Given AlloyDB env vars set, When loadCatalog runs, Then it still loads
// products.json with no network/DB attempt.
func TestLoadCatalog_AlloyDBEnvSet_StillLoadsProductsJSON(t *testing.T) {
	t.Setenv("ALLOYDB_CLUSTER_NAME", "dummy-cluster")
	t.Setenv("PROJECT_ID", "dummy-project")
	t.Setenv("REGION", "dummy-region")

	assertLoadsLocalCatalog(t)
}
