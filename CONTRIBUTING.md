# Contributing

Thanks for contributing to SkillWeave.

## Principles

- keep the core simple
- prefer explicit structure over clever prompting
- keep examples realistic
- keep formats stable
- optimize for portability across agent runtimes

## How to contribute

1. Open an issue or discuss the change first for larger changes.
2. Keep pull requests focused and small.
3. Add or update tests when changing parser, validator, or orchestrator logic.
4. Update docs and examples if the format changes.

## Areas where contributions are welcome

- prompt-sequence examples
- validation rules
- parser robustness
- orchestration improvements
- docs and templates
- JSON schema refinements

## Style guidance

- clear naming
- small modules
- explicit error handling
- no unnecessary abstractions

## Release Process

### Versioning
- Follow semantic versioning (MAJOR.MINOR.PATCH)
- Update `CHANGELOG.md` before creating a release
- Include all significant changes in the changelog entry

### Release Titles
- **Release titles must follow the format:** `SkillWeave vX.Y.Z`
- Do not add subtitles, descriptions, or additional text to the release title
- Example: `SkillWeave v0.3.1` ✅
- Example: `SkillWeave v0.3.1 - Fixed installer` ❌

### Release Notes
- Use the changelog entry as the basis for release notes
- Include installation instructions for the current version
- Include usage examples
- Mention significant fixes and improvements

### Creating a Release
1. Ensure all changes are committed and pushed
2. Create and push a git tag: `git tag -a vX.Y.Z -m "SkillWeave vX.Y.Z"`
3. Push the tag: `git push origin vX.Y.Z`
4. Create the GitHub release with the exact title `SkillWeave vX.Y.Z`
