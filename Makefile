# IMU Telemetry System — Build Targets

PROTO_DIR   := shared_contracts
DART_OUT    := mobile_node/lib/models
PYTHON_OUT  := master_backend/proto

.PHONY: proto proto-dart proto-python install-backend install-frontend help start ip doctor stop

## Generate Protobuf bindings for all targets
proto: proto-dart proto-python

proto-dart:
	@echo "Generating Dart protobuf bindings..."
	protoc \
	  --dart_out=grpc:$(DART_OUT) \
	  -I $(PROTO_DIR) \
	  $(PROTO_DIR)/sensor_packet.proto \
	  $(PROTO_DIR)/commands.proto
	@echo "Done: $(DART_OUT)"

proto-python:
	@echo "Generating Python protobuf bindings..."
	protoc \
	  --python_out=$(PYTHON_OUT) \
	  -I $(PROTO_DIR) \
	  $(PROTO_DIR)/sensor_packet.proto \
	  $(PROTO_DIR)/commands.proto
	@echo "Done: $(PYTHON_OUT)"

## Install backend Python dependencies
install-backend:
	cd master_backend && pip install -r requirements.txt

## Install frontend Node dependencies
install-frontend:
	cd master_frontend && npm install

## Run backend dev server (from repo root)
run-backend:
	python master_backend/run.py

## Run frontend dev server
run-frontend:
	cd master_frontend && npm run dev

## Start backend + frontend together (assumes env + build ready)
start:
	powershell -NoProfile -ExecutionPolicy Bypass -File start.ps1

## Show backend LAN IP + health without stopping the server
ip doctor:
	powershell -NoProfile -ExecutionPolicy Bypass -File ops/ip.ps1

## Stop backend + frontend
stop:
	powershell -NoProfile -ExecutionPolicy Bypass -File ops/stop.ps1

help:
	@grep -E '^##' Makefile | sed 's/## //'
