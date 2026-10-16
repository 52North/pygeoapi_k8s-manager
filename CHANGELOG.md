# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.30] - 2026-10-16

### Added

- `CONTRIBUTING.md` with the contribution guidelines.
- `CHANGELOG.md`to keep track of the project's development.

### Changed

- README "Contribute" section now links to `CONTRIBUTING.md`.
- kind set-up: MinIO replaced by [SILO](https://github.com/pgsty/silo)
- Raised minimum dependency versions:
  - boto3 >= 1.43.101 (capped by aiobotocore, see Fixed),
  - botocore >= 1.43.101,
  - filelock >= 4.2.0,
  - pytest-cov >= 7.1.0 (dev),
  - ruff >= 0.17.1 (dev) and
  - time-machine >= 3.5.1 (dev).
- Updated locked dependencies, incl.
  - affine 3.0.1,
  - boto3/botocore 1.43.106,
  - cryptography 50.0.2,
  - filelock 4.2.0,
  - google-auth 2.62.0,
  - oauthlib 4.0.0,
  - pydantic 2.14.1,
  - pyproj 3.8.0,
  - shapely 2.2.0,
  - sqlalchemy 2.1.4,
  - urllib3 2.8.0 and
  - werkzeug 3.1.9.
- CI:
  - actions/stale v10 → v11,
  - astral-sh/setup-uv v9.0.0 → v10.3.0.
- Updated `NOTICE` file.

### Removed

- Transitive dependencies cligj and greenlet are no longer locked.

### Fixed

- Container image: upgrade `s3fs` (2021.7.0, from the pygeoapi base image) to >= 2026.6.0 to get `fsspec` >= 2026.6.0 fixing CVE-2026-104851. Dependabot ignores boto3/botocore >= 1.43.107 until `aiobotocore` supports them.
- TwinShip project logo filename and its README reference.

## [0.29] - 2026-07-29

### Changed

- Upgraded pygeoapi 0.23.5 → 0.24.0.
- Improved kind documentation.

### Fixed

- "mimetype" annotation problem ([#51](https://github.com/52North/pygeoapi_k8s-manager/issues/51)).

## [0.28] - 2026-07-27

### Added

- Allow overwriting the metadata of the hello world K8s processor.

### Changed

- Upgraded pygeoapi 0.23.4 → 0.23.5.
- Updated dependencies, e.g. setuptools and pyasn1.
- Extended kind documentation and example.
- Improved test coverage.
- Adjusted build pipeline to allowed input values.

### Fixed

- Namespace in example `kustomization.yaml`.
- Wrong retention period of the full CVE report in the documentation.

## [0.27] - 2026-06-22

### Added

- Configurable `securityContext` for spawned job pods.
- Process input validation.
- Non-blocking full Trivy report as pipeline artefact incl. documented scanning policy.
- Weekly Dependabot checks for uv dependencies.
- Enforced minimum test coverage in CI.
- Documentation of the job name prefix as fixed deploy-time setting.
- Documentation of the K8s client library version handling.

### Changed

- Upgraded pygeoapi 0.23.3 → 0.23.4.
- Updated jinja2, requests, pyyaml, cryptography, urllib3 and idna.
- Broader ruff rule set, `dict.get` refactoring and stricter error handling.
- Consistent build-args (`VERSION`/`BUILD_DATE`) in CI.

### Removed

- Duplicate `docker` dependency group.

### Fixed

- Finalizer was always configured, leaving pods stuck in `Terminating`.
- Pipeline and documented commands.

### Security

- Hardened API token authentication: constant-time comparison, no token in logs or K8s objects.

## [0.26] - 2026-04-24

### Changed

- Upgraded pygeoapi 0.23.2 → 0.23.3.
- Upgraded kind cluster v1.32.11 → v1.33.7.
- Renamed pipeline steps.
- Dependency updates.

## [0.25] - 2026-04-17

### Changed

- Upgraded pygeoapi 0.23.1 → 0.23.2 and kubernetes client to 33.
- Improved build pipeline.
- Updated kind instructions.
- Dependency updates.

### Security

- Fixed pipeline because of the Trivy supply chain issue
  ([GHSA-69fq-xp46-6x23](https://github.com/aquasecurity/trivy/security/advisories/GHSA-69fq-xp46-6x23)).

## [0.24] - 2026-03-19

### Changed

- Upgraded pygeoapi 0.23.0 → 0.23.1.

## [0.23] - 2026-03-10

### Added

- Script to generate the `NOTICE` file.
- Command to tag the image in the kind instructions.

### Changed

- Switched to new upstream pygeoapi 0.20.0 → 0.23.0.
- Increased Python version 3.10 → 3.12.
- Increased kind node version 1.31.9 → 1.32.11.
- Improved kind instructions.
- Updated `NOTICE`.
- Security and dependency updates.

### Fixed

- Job result retrieval of the hello_world process.

## [0.22] - 2025-11-26

### Added

- Contributing documentation.
- Issue templates.
- Source file headers and README notice regarding pygeoapi-kubernetes-papermill.
- TwinShip in the funding section.

### Changed

- CVE scan result notifications are sent to Google Chat instead of Slack.
- Updated pipeline defaults and stale action configuration.
- Improved documentation.
- Dependency updates.

### Fixed

- Do not try to handle job pods that do not exist.
- YAML syntax in pipeline.
- Links in funding table.

## [0.21] - 2025-06-25

### Fixed

- Duplicate log upload by skipping already processed jobs.

## [0.20] - 2025-06-25

### Added

- Process id is added to the env of each container by default.

## [0.19] - 2025-06-23

### Added

- Documentation of the result handling.

### Changed

- More generic result annotation handling.

## [0.18] - 2025-06-23

### Added

- Support for result annotations.
- Upload logs of all containers incl. init containers.

### Changed

- Updated description and contributors in `pyproject.toml`.

## [0.17] - 2025-06-18

### Changed

- Migrated to [astral.sh/uv](https://docs.astral.sh/uv/).

## [0.16.1] - 2025-06-10

### Fixed

- Finalizer used the class name instead of the constructor.

## [0.16] - 2025-06-10

### Added

- Tests for execution authentication, processor rejection and `NotImplementedError`s.
- Init job for the MinIO set-up in the kind cluster.

### Changed

- Refactored finalizer to watch job events; rewrote `controller_loop()`.
- Refactored kind set-up incl. working log finalizer bucket.
- Simplified hello_world_k8s.
- Minor adjustments to example configurations and job creation.

### Removed

- Unused env variable and skipped tests.

### Fixed

- Log finalizer permission configuration and handling of K8s events.
- Command handling in hello_world_k8s.
- kind set-up.

## [0.15.2] - 2025-05-27

### Fixed

- Handling of `image_pull_secrets`.

## [0.15.1] - 2025-05-27

### Fixed

- Optional missing `command` in processor definition.

## [0.15] - 2025-05-27

### Added

- Support for `init_containers`.
- Support for `emptyDir` storage in `GenericImageProcessor`.
- pygeoapi job id in env of all containers.
- Local test set-up with kind.
- Credits / funding information.
- Tests for default, finalizer, toleration and annotation config of new K8s jobs.

### Changed

- Extracted `finalizer.KubernetesFinalizerController` from manager.
- K8s job annotations `_START` and `_UPDATED` are set to the same value during creation.
- Updated and sorted `NOTICE`.

### Fixed

- Auth token checking.

## [0.14] - 2025-05-15

### Changed

- Improved finalizer management.

## [0.13] - 2025-05-15

### Added

- Finalizer in pod template metadata.

### Changed

- Refactoring.

## [0.12] - 2025-05-15

### Changed

- Switched event selection in K8s finalizer loop.

## [0.11] - 2025-05-15

### Fixed

- Toleration addition.

## [0.10] - 2025-05-14

### Added

- Tolerations.
- Tests in push checks.

### Changed

- `VERSION` is a build `ARG` instead of `ENV`.
- Sorted imports.

### Fixed

- Bug in `generic_image.py`.
- Missing `VERSION` env in pipeline and default in Dockerfile.

### Security

- Credentials/token are logged only on DEBUG level.

## [0.9] - 2025-05-13

### Added

- Job log finalizer incl. finalizer controller loop.
- Tests in build pipeline and more unit tests.
- Log format incl. process id.

### Changed

- Switched linting from flake8 to ruff incl. format checks in pipelines.
- Stale bot runs weekly instead of daily.
- Refactoring.

### Fixed

- Inverted result of `manager.check_s3_upload_variables()`.

## [0.8.1] - 2025-04-29

### Added

- Stale bot.

### Fixed

- `SyntaxError: f-string: unmatched '['`.

## [0.8] - 2025-04-24

### Changed

- Improved error handling incl. tests.

## [0.7] - 2025-04-24

### Fixed

- Handling of absent pods and logs.
- Missing env variable in workflow.

## [0.6] - 2025-04-23

### Added

- Deployment information.
- Documentation and examples for K8s configuration.

### Fixed

- Build information.

## [0.5] - 2025-04-03

### Added

- Build pipeline.

### Changed

- Increased K8s version.
- Image polishing and build info adjustments.

## [0.4] - 2025-04-02

### Added

- Inject inputs via env variable `PYGEOAPI_K8S_MANAGER_INPUTS`.
- First storage support.
- Handling of not specified resources and env.

### Changed

- Extended `GenericImageProcessor` documentation.

## [0.3] - 2025-03-31

### Added

- First working version of `GenericImageProcessor` incl. environment, resources and
  tolerations parsing and example configuration.
- Token protection for each `KubernetesManager` execution.
- Support for not specified `image_pull_secret`.
- Check for too long keys.

### Changed

- Improved hello_world_k8s incl. tests.

### Removed

- `typed_json_dataclass` dependency.

### Fixed

- `None` mimetype links.
- Wrong `container.command` testing.

## [0.2] - 2025-03-28

### Added

- Hello world processor.
- License information.

### Changed

- Upgraded pygeoapi 0.19.0 → 0.20.0.
- Improved build info display and documentation.

## [0.1] - 2025-03-26

### Added

- Initial release of the pygeoapi job manager using the K8s API server.
- Namespace configuration via env variable for non in-cluster deployment.
- Log level configuration for job manager dependencies.
- Non-confidential build information at `host/static/info.txt`.
- Image handling instructions.

### Security

- Mitigated CVEs of the base image OS.

[0.30]: https://github.com/52North/pygeoapi_k8s-manager/compare/v0.29...v0.30
[0.29]: https://github.com/52North/pygeoapi_k8s-manager/compare/v0.28...v0.29
[0.28]: https://github.com/52North/pygeoapi_k8s-manager/compare/v0.27...v0.28
[0.27]: https://github.com/52North/pygeoapi_k8s-manager/compare/v0.26...v0.27
[0.26]: https://github.com/52North/pygeoapi_k8s-manager/compare/v0.25...v0.26
[0.25]: https://github.com/52North/pygeoapi_k8s-manager/compare/v0.24...v0.25
[0.24]: https://github.com/52North/pygeoapi_k8s-manager/compare/v0.23...v0.24
[0.23]: https://github.com/52North/pygeoapi_k8s-manager/compare/v0.22...v0.23
[0.22]: https://github.com/52North/pygeoapi_k8s-manager/compare/v0.21...v0.22
[0.21]: https://github.com/52North/pygeoapi_k8s-manager/compare/v0.20...v0.21
[0.20]: https://github.com/52North/pygeoapi_k8s-manager/compare/v0.19...v0.20
[0.19]: https://github.com/52North/pygeoapi_k8s-manager/compare/v0.18...v0.19
[0.18]: https://github.com/52North/pygeoapi_k8s-manager/compare/v0.17...v0.18
[0.17]: https://github.com/52North/pygeoapi_k8s-manager/compare/v0.16.1...v0.17
[0.16.1]: https://github.com/52North/pygeoapi_k8s-manager/compare/v0.16...v0.16.1
[0.16]: https://github.com/52North/pygeoapi_k8s-manager/compare/v0.15.2...v0.16
[0.15.2]: https://github.com/52North/pygeoapi_k8s-manager/compare/v0.15.1...v0.15.2
[0.15.1]: https://github.com/52North/pygeoapi_k8s-manager/compare/v0.15...v0.15.1
[0.15]: https://github.com/52North/pygeoapi_k8s-manager/compare/v0.14...v0.15
[0.14]: https://github.com/52North/pygeoapi_k8s-manager/compare/v0.13...v0.14
[0.13]: https://github.com/52North/pygeoapi_k8s-manager/compare/v0.12...v0.13
[0.12]: https://github.com/52North/pygeoapi_k8s-manager/compare/v0.11...v0.12
[0.11]: https://github.com/52North/pygeoapi_k8s-manager/compare/v0.10...v0.11
[0.10]: https://github.com/52North/pygeoapi_k8s-manager/compare/v0.9...v0.10
[0.9]: https://github.com/52North/pygeoapi_k8s-manager/compare/v0.8.1...v0.9
[0.8.1]: https://github.com/52North/pygeoapi_k8s-manager/compare/v0.8...v0.8.1
[0.8]: https://github.com/52North/pygeoapi_k8s-manager/compare/v0.7...v0.8
[0.7]: https://github.com/52North/pygeoapi_k8s-manager/compare/v0.6...v0.7
[0.6]: https://github.com/52North/pygeoapi_k8s-manager/compare/v0.5...v0.6
[0.5]: https://github.com/52North/pygeoapi_k8s-manager/compare/v0.4...v0.5
[0.4]: https://github.com/52North/pygeoapi_k8s-manager/compare/v0.3...v0.4
[0.3]: https://github.com/52North/pygeoapi_k8s-manager/compare/v0.2...v0.3
[0.2]: https://github.com/52North/pygeoapi_k8s-manager/compare/v0.1...v0.2
[0.1]: https://github.com/52North/pygeoapi_k8s-manager/releases/tag/v0.1
