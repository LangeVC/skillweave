# Prompt-Sequence Specification (v2 Ralph Loop Example)

## Metadata
- title: API Service Implementation with Ralph Loop
- version: 2.0
- language: en
- domain: backend development
- intent: implement
- complexity: high
- sequence_type: build
- execution_mode: ralph_attended

## Objective
Implement a complete REST API service with authentication, database integration, tests, and documentation using Ralph Loop execution.

## Success Criteria
- All endpoints work correctly (200/400/401/404 responses)
- Authentication middleware validates tokens
- Database operations are transactional
- Unit tests cover >90% of code
- Integration tests verify API flows
- Documentation includes OpenAPI spec
- Performance benchmarks meet requirements

## Assumptions
- Using Node.js/Express or similar framework
- PostgreSQL database available
- JWT for authentication
- Docker for containerization
- CI/CD pipeline configured

## Usage Notes
- web_research: optional
- citations: optional
- intermediate_validation: required
- ask_for_clarification: only_if_blocked
- execution_mode: ralph_attended
- fallback_behavior: stop_and_report_with_retry
- output_style: technical_with_gates
- binary_gates: required

## Inputs Required
- API specification (OpenAPI or similar)
- Database schema
- Authentication requirements
- Performance requirements (latency, throughput)
- Deployment environment details

## Outputs Required
- Complete API implementation
- Unit test suite
- Integration test suite
- Docker configuration
- OpenAPI documentation
- Performance benchmarks
- Deployment instructions

## Sequence Steps

### Step 1: Setup Project Structure
- **id**: "SETUP-001"
- **title**: "Initialize project structure and dependencies"
- **type**: "setup"
- **depends_on**: []
- **required_capabilities**: ["code_generation", "configuration"]
- **write_scope**: ["package.json", "tsconfig.json", "Dockerfile", ".env.example"]
- **verification**: ["package.json validates", "TypeScript compiles", "Dockerfile builds"]
- **integration_gate**: "post"
- **retry_budget**: 1
- **handoff_contract**: ["project_initialized", "dependencies_installed", "build_configuration"]
- **parallelizable**: false
- **must_stay_local**: true

**Action**: Create project structure with proper TypeScript configuration, install dependencies, set up Docker, configure environment variables.

### Step 2: Implement Database Layer
- **id**: "DB-001"
- **title**: "Implement database models and migrations"
- **type**: "database"
- **depends_on**: ["SETUP-001"]
- **required_capabilities**: ["code_generation", "database_design"]
- **write_scope**: ["src/models/", "src/migrations/", "src/repositories/"]
- **verification**: ["migrations run successfully", "models validate against schema", "repositories compile"]
- **integration_gate**: "both"
- **retry_budget**: 2
- **handoff_contract**: ["models_implemented", "migrations_created", "repositories_tested"]
- **parallelizable**: false
- **must_stay_local**: true

**Action**: Create database models, migrations, and repository layer with proper TypeScript types and validation.

### Step 3: Implement Authentication Middleware
- **id**: "AUTH-001"
- **title**: "Implement JWT authentication middleware"
- **type**: "authentication"
- **depends_on**: ["SETUP-001"]
- **required_capabilities**: ["code_generation", "security"]
- **write_scope**: ["src/middleware/auth.ts", "src/utils/jwt.ts", "tests/middleware/auth.test.ts"]
- **verification**: ["JWT tokens validate correctly", "middleware rejects invalid tokens", "tests pass"]
- **integration_gate**: "post"
- **retry_budget**: 2
- **handoff_contract**: ["auth_middleware_implemented", "jwt_utils_tested", "security_audit_passed"]
- **parallelizable**: true
- **must_stay_local**: false

**Action**: Implement JWT token validation, authentication middleware, and security utilities.

### Step 4: Implement Core API Endpoints
- **id**: "API-001"
- **title**: "Implement REST API endpoints"
- **type**: "api"
- **depends_on**: ["DB-001", "AUTH-001"]
- **required_capabilities**: ["code_generation", "api_design"]
- **write_scope**: ["src/routes/", "src/controllers/", "src/validators/"]
- **verification**: ["endpoints respond correctly", "validation works", "error handling proper"]
- **integration_gate**: "both"
- **retry_budget**: 3
- **handoff_contract**: ["endpoints_implemented", "validation_complete", "error_handling_tested"]
- **parallelizable**: false
- **must_stay_local**: true

**Action**: Implement REST endpoints with proper routing, controllers, validation, and error handling.

### Step 5: Write Unit Tests
- **id**: "TEST-001"
- **title**: "Write comprehensive unit tests"
- **type**: "testing"
- **depends_on**: ["DB-001", "AUTH-001", "API-001"]
- **required_capabilities**: ["testing", "code_analysis"]
- **write_scope**: ["tests/unit/"]
- **verification**: ["test coverage >90%", "all tests pass", "edge cases covered"]
- **integration_gate**: "post"
- **retry_budget**: 2
- **handoff_contract**: ["test_coverage_report", "tests_passing", "edge_cases_documented"]
- **parallelizable**: true
- **must_stay_local**: false

**Action**: Write unit tests for all components with high coverage and edge case testing.

### Step 6: Write Integration Tests
- **id**: "TEST-002"
- **title**: "Write API integration tests"
- **type**: "testing"
- **depends_on**: ["API-001", "TEST-001"]
- **required_capabilities**: ["testing", "api_testing"]
- **write_scope**: ["tests/integration/"]
- **verification**: ["API flows work end-to-end", "authentication tests pass", "database integration works"]
- **integration_gate**: "post"
- **retry_budget**: 2
- **handoff_contract**: ["integration_tests_passing", "api_flows_verified", "performance_measured"]
- **parallelizable**: true
- **must_stay_local**: false

**Action**: Write integration tests that verify complete API flows including authentication and database operations.

### Step 7: Create Documentation
- **id**: "DOC-001"
- **title**: "Create comprehensive documentation"
- **type**: "documentation"
- **depends_on**: ["API-001"]
- **required_capabilities**: ["documentation", "technical_writing"]
- **write_scope**: ["docs/", "README.md", "openapi.yaml"]
- **verification**: ["OpenAPI spec valid", "README complete", "examples work"]
- **integration_gate**: "post"
- **retry_budget**: 1
- **handoff_contract**: ["documentation_complete", "openapi_spec_valid", "examples_tested"]
- **parallelizable**: true
- **must_stay_local**: false

**Action**: Create OpenAPI specification, README, usage examples, and deployment instructions.

### Step 8: Performance Optimization
- **id**: "PERF-001"
- **title**: "Optimize performance and run benchmarks"
- **type**: "optimization"
- **depends_on**: ["API-001", "TEST-002"]
- **required_capabilities**: ["performance", "profiling"]
- **write_scope**: ["benchmarks/", "src/optimizations/"]
- **verification**: ["meets latency requirements", "handles expected load", "memory usage optimized"]
- **integration_gate**: "post"
- **retry_budget**: 2
- **handoff_contract**: ["performance_benchmarks", "optimizations_applied", "requirements_met"]
- **parallelizable**: true
- **must_stay_local**: false

**Action**: Profile application, optimize performance, run load tests, verify requirements are met.

## Final Assembly
- Combine all components into working application
- Verify all integration points
- Run full test suite
- Generate final deliverables package

## Validation Rules
- All tests must pass (unit, integration, performance)
- OpenAPI spec must validate
- Docker image must build successfully
- Performance benchmarks must meet requirements
- Code coverage must be >90%
- Security audit must pass

## Failure Handling
- If any step fails, apply retry budget
- If retry budget exhausted, stop and report
- Provide detailed error analysis
- Suggest specific fixes
- Allow partial completion with clear status

## Final Deliverable Format
- Complete source code with tests
- Docker configuration
- OpenAPI specification
- Performance benchmarks
- Deployment instructions
- Security audit report

## Ralph Loop Configuration
- **execution_mode**: ralph_attended
- **batch_strategy**: dependency_clusters
- **parallel_lanes**: 3 max
- **gate_policy**: binary_only
- **retry_strategy**: narrow_fixes
- **completion_signal**: all_gates_passed
- **memory_tracking**: structured_yaml

## Batch Planning (Example)
- **Batch 1**: SETUP-001 (critical path)
- **Batch 2**: DB-001, AUTH-001 (parallel lanes)
- **Batch 3**: API-001 (critical path, depends on Batch 2)
- **Batch 4**: TEST-001, DOC-001 (parallel sidecars)
- **Batch 5**: TEST-002, PERF-001 (parallel sidecars)
- **Integration Gates**: After Batches 2, 3, and 5

## Expected Ralph Loop Behavior
1. **Preflight**: Analyze sequence, plan batches, identify safe lanes
2. **Batch 1**: Setup project (critical path, local)
3. **Batch 2**: Database + Auth (parallel lanes, subagents)
4. **Integration Gate 1**: Verify DB+Auth integration
5. **Batch 3**: API endpoints (critical path, local)
6. **Batch 4**: Unit tests + Docs (parallel sidecars)
7. **Batch 5**: Integration tests + Performance (parallel sidecars)
8. **Integration Gate 2**: Full system verification
9. **Review Gate**: Human review of implementation
10. **Advance**: Mark complete, deliver package