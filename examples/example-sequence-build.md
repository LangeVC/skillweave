# Prompt-Sequence Specification

## Metadata
- title: Web Component Implementation
- version: 0.1
- language: en
- domain: web development
- intent: implement
- complexity: medium
- mode: build

## Objective
Create a reusable web component with TypeScript, tests, and documentation.

## Success Criteria
- Component renders correctly
- TypeScript types are strict
- Unit tests pass
- Documentation includes usage examples
- Accessible (ARIA attributes)

## Assumptions
- Using LitElement or similar library
- Build tooling (Vite) is available
- Target browsers support ES modules

## Usage Notes
- web_research: optional
- citations: optional
- intermediate_validation: required
- ask_for_clarification: only_if_blocked
- execution_mode: parallel
- fallback_behavior: stop_and_report
- output_style: technical

## Inputs Required
- Component name
- Props/attributes list
- Styling requirements (CSS framework)
- Test framework preference

## Outputs Required
- TypeScript component file
- Unit test file
- Documentation (README section)
- Example usage snippet
- Package.json updates (if needed)

## Sequence Steps

### Step 1
- id: step-01
- name: Component scaffolding
- purpose: Set up basic component structure
- depends_on: []
- instructions: |
    Create a LitElement component with the given name. Define the properties and attributes based on the input list. Include default values and type annotations.
- expected_output:
    - TypeScript component file with class definition
    - Property declarations with @property decorators
- validation:
    - Component class extends LitElement
    - Properties are correctly typed
- completion_rule:
    - File saved as `src/components/{component-name}.ts`

### Step 2
- id: step-02
- name: Template and rendering
- purpose: Implement render method and template
- depends_on: [step-01]
- instructions: |
    Implement the `render()` method returning a `html` template. Include slots, event handlers, and conditional rendering if needed. Ensure accessibility attributes are included.
- expected_output:
    - Complete render method with template
    - ARIA attributes where appropriate
- validation:
    - Template is syntactically valid
    - Accessibility attributes present
- completion_rule:
    - Component renders without errors in browser

### Step 3
- id: step-03
- name: Styling
- purpose: Add CSS styles
- depends_on: [step-02]
- instructions: |
    Add styles using `static styles` property. Use CSS custom properties for theming. Ensure responsive design if required.
- expected_output:
    - CSS styles integrated
    - Custom properties for theming
- validation:
    - Styles are scoped to component
    - No conflicts with global styles
- completion_rule:
    - Component visually matches requirements

### Step 4
- id: step-04
- name: Unit tests
- purpose: Create test suite
- depends_on: [step-01]
- instructions: |
    Write unit tests using the preferred test framework (e.g., Jest + @web/test-runner). Test property updates, events, and rendering.
- expected_output:
    - Test file with at least 5 test cases
    - Coverage for main functionality
- validation:
    - Tests pass
    - Edge cases covered
- completion_rule:
    - Test suite passes with 100% component logic coverage

### Step 5
- id: step-05
- name: Documentation
- purpose: Generate usage documentation
- depends_on: [step-01, step-02, step-03]
- instructions: |
    Create a README section for the component. Include installation, API reference, examples, and accessibility notes.
- expected_output:
    - Markdown documentation
    - Code examples
    - Prop table
- validation:
    - Documentation is clear and complete
    - Examples run correctly
- completion_rule:
    - Documentation added to project README

### Step 6
- id: step-06
- name: Integration and build
- purpose: Ensure component works in build system
- depends_on: [step-01, step-02, step-03, step-04]
- instructions: |
    Verify component builds with Vite/Rollup. Check bundle size and export correctly.
- expected_output:
    - Successful build
    - No warnings
- validation:
    - Bundle size within limits
    - Exports are correct
- completion_rule:
    - Component can be imported and used in a sample app

## Final Assembly
Combine all generated artifacts into a cohesive package. Ensure the component is ready for distribution or integration into the larger project.

## Validation Rules
- All steps must pass validation before moving to next step
- Code must follow project coding standards
- No lint errors
- All tests pass

## Failure Handling
If any step fails, report the error and pause execution. Offer to retry with adjusted parameters or skip if possible.

## Final Deliverable Format
- Source code files (.ts, .css)
- Test files (.test.ts)
- Documentation (.md)
- Example usage snippet
- Build configuration updates if needed