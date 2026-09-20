# Third-party notices and release constraints

This file identifies material that is not relicensed by the repository's
Apache-2.0 and CC BY 4.0 grants. It is an inventory aid, not a substitute for the
applicable terms.

## Package dependencies

JavaScript, .NET, Python, container, and operating-system dependencies retain
their own licenses. Lockfiles record direct and transitive package versions; they
do not replace the license and notice files required when distributing compiled
packages or container images. Produce and review a complete dependency notice
bundle before a binary or image release.

## Olist Brazilian E-Commerce dataset

The optional Olist adapter downloads external data at the user's request. Raw and
processed Olist data are ignored and are not part of this repository. The source
dataset is described as CC BY-NC-SA 4.0; its attribution, non-commercial, and
share-alike requirements apply independently. See the dataset source linked from
[`docs/data-sources.md`](docs/data-sources.md).

## SemIf

The optional local decision backend uses SemIf at commit
`ca3ba65f142967030ecb453346e94d6f476a69df`. SemIf is licensed under the MIT
License, copyright (c) 2026 TheoLeeCJ. Its license and source are available in
the [SemIf repository](https://github.com/TheoLeeCJ/SemIf). SemIf is an
independent project and is not affiliated with TypeSafe.

## Qwen3.5-4B and MLX

The SemIf backend downloads `Qwen/Qwen3.5-4B` at revision
`851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a`. The model is distributed under
Apache-2.0. Model weights remain in the user's Hugging Face cache and are not
included in this repository. See the
[Qwen3.5-4B model card](https://huggingface.co/Qwen/Qwen3.5-4B).

SemIf's Apple Silicon backend uses MLX and MLX-LM, distributed under the MIT
License, copyright (c) 2023 Apple Inc. The worker lockfile pins the exact
dependency graph used by the integration.

## OpenAI and other model output

AI-reference labels and recorded model outputs remain subject to the applicable
provider terms and to any rights in their inputs. The repository licenses only
the project-authored selection, arrangement, annotations, and narrative to the
extent those rights are held. Review provider terms before redistribution.
