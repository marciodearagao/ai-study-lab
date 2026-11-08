# AI Study Lab — UI/UX Pending Fixes

**Status:** Deferred
**Target:** Post-v0.2.0
**Candidate milestone:** v0.2.1 (not yet scheduled)
**Scope:** Official Learning Paths lesson view, desktop/laptop
**Approved reference:** `design-prototypes/prototype-a.html`, `prototype-a.css`, and shared `prototype.css`
**Evidence:** User-provided screenshots, November 7, 2026: `image(20261107-210457).png` (running ASL) and `image(20261107-210542).png` (Prototype A)
**Review method:** Visual comparison of screenshots and the Codex implementation report. No live browser DOM, computed-style inspection, or repository inspection performed in this review. Relative positions are qualitative, not pixel-verified.

## Decision and release boundary

The current implementation is **functionally useful but not yet a faithful reproduction of Prototype A**. Stop iterative visual tweaks for now. Do not block v0.2.0 for nonessential visual differences. Revisit the items below in a dedicated post-0.2.0 visual-fidelity pass, after checking that normal course navigation, quiz submission, saved completion, and auto-resume work. A confirmed failure in those functional flows must be triaged separately before release.

## What is already improved

- The running app now displays one prominent lesson title, instead of two duplicated titles.
- The extra path-selection card above the sidebar is no longer visible while reading a lesson.
- The breadcrumb is above the course columns.
- One course-navigation panel shows the real path, progress, module, active lesson, and completion.
- The reading column is wider than before; the quiz is integrated below the explanation, and its submission button is left-aligned.
- The existing cream/forest-green/clay visual language and typography remain recognizable.

These are genuine improvements. The remaining mismatch is partly **structural/detail-level** and partly because the prototype uses fictional content and progress states.

## Pending differences — compare at the same viewport and zoom

| Priority | Area | Running app (screenshot 1) | Approved Prototype A (screenshot 2) | Proposed later correction / acceptance |
|---|---|---|---|---|
| **P1 visual** | Sidebar header hierarchy | `Course Content` is followed immediately by `← All learning paths`, with no compact progress summary in the header. | `Course Content` is paired with a small right-aligned path/completion summary; navigation back is located elsewhere in the composition. | Match the prototype's **header hierarchy and spacing**, but retain a clearly discoverable `All learning paths` action. Do not duplicate progress information unnecessarily. |
| **P1 visual** | Sidebar internal composition | Large gap/divider between progress and the lone module, followed by one wider highlighted row; the real sidebar looks sparse and structurally different from the example. | A compact hierarchy with module counts, completed/active indicators, consistent row dimensions, and several modules. | Align padding, separators, row sizing, module heading placement, and active/completed states using **real** modules/lessons. Test with a temporary multi-module fixture, not new official content. A sidebar with one real lesson will naturally remain shorter. |
| **P1 visual** | Lesson metadata and heading | Only `Lesson completed previously.` appears above the main title, with little information on lesson position. | Small `Introduction · Lesson 2 of 6` context appears above the heading; a status appears separately on the right. | Add/position accurate module and lesson-position context **only if derivable from the existing content**. Show completion state truthfully and consistently; don't copy `In progress` or `Lesson 2 of 6` for the actual completed single lesson. |
| **P2 visual** | Reading-area alignment/vertical rhythm | Course heading, title, paragraphs, and quiz have noticeably different vertical pacing from the prototype; the live page reads as slightly larger/looser. | More compact metadata/title rhythm and different spacing between content sections. | At identical viewport/zoom, compare computed margin, padding, font-size, line-height, and column start for breadcrumb, heading, body, quiz, and pager; adjust only demonstrated discrepancies. |
| **P2 visual** | Lesson content structure | The real lesson is three short paragraphs with no intermediate section heading. | The prototype includes a `Learning from examples` section heading and a different arrangement of sample text. | **Not a CSS defect.** Keep actual Markdown unchanged. Do not add fictitious headings/text to mimic the prototype. Validate styling instead using a temporary sample fixture with headings, code and lists. |
| **P2 visual** | Quiz heading and metadata | The app says `Lesson quiz` with `QUESTION 1 OF 4` directly below; layout is more compact. | `CHECK YOUR UNDERSTANDING` eyebrow + `Quick quiz`, with question count on the right. | Match typography, eyebrow/counter placement and spacing if desired. Preserve the app's real question count, messages and persistence states. Do not copy prototype phrasing unless deliberately approved. |
| **P2 visual** | Quiz answer affordances | App shows one circular letter marker per choice with no separate radio circle. | Prototype shows a selection circle **plus** a letter badge, creating a clearer selection affordance. | Decide whether to add a native-looking radio indicator; retain current accessible button interaction and keyboard support. Verify selected/correct/incorrect/disabled states, not just the initial state. |
| **P2 visual** | Quiz and pager spacing | App's submission/pager spacing and visual weight differ from the prototype. | Slightly different button sizing, borders, and separation from quiz body. | Compare matched states at the same viewport, then adjust borders, padding and vertical rhythm without changing navigation or persistence. |
| **P3 / future** | Floating AI mentor | Not yet integrated into running application. | Prototype shows the small green orb near the bottom-right. | Integrate later in a separate approved step. Keep a subtle motion/reduced-motion treatment; avoid overlaying quiz controls. Not required for v0.2.0. |

## Differences that are intentional — do not “fix” by copying demo data

- **Progress:** running ASL reports **1/1 lessons completed (100%)**; Prototype A displays **1/6 completed (17%)**. The prototype's figures are examples, not a visual acceptance target.
- **Sidebar contents:** running ASL has one official lesson; the prototype has fictitious extra lessons/modules. Do not populate real course content to fill space.
- **Status:** `Lesson completed previously` is valid for the user's saved state. Prototype's `In progress` illustrates another state.
- **Previous/Next:** running app disables both controls because there is only one lesson; prototype illustrates available navigation. Keep real boundary behavior.
- **Lesson body and quiz wording:** different Markdown/questions naturally cause different page height and wrapping; this does not imply a layout defect.

## Why earlier changes did not feel successful

1. The Codex iterations mostly proved **source rules and application behavior**, not matching browser renderings.
2. Visual acceptance was not performed against the **same viewport, zoom, fixture content and UI state**.
3. The prototype's fictitious six-lesson scenario was repeatedly compared with the real one-lesson, completed scenario. These cannot match element for element without deliberately equivalent fixtures.
4. Some original application navigation elements and wording remain by design; these need explicit approval decisions, not arbitrary CSS overrides.
5. An end-to-end review of the whole screen was missing, so independent small CSS fixes did not converge on the approved composition.

## Future visual-fidelity work plan — after v0.2.0

1. **Freeze and preserve evidence.** Keep the two November 7 screenshots and the approved prototype as the baseline. No further styling changes during release closure unless they fix a functional blocker.
2. **Match conditions.** Capture both pages in one browser at identical viewport width/height, browser zoom (100%), device pixel ratio where feasible, and comparable UI states. Use a *temporary* multi-lesson test fixture when evaluating module hierarchy and lesson navigation.
3. **Inspect computed layout and DOM.** Compare the actual bounding boxes and computed CSS (not only declared source values) for header, breadcrumb, course grid, sidebar, content, quiz, and pager; check specificity/overrides and hidden elements.
4. **Fix sidebar and metadata first.** Reproduce the prototype's course-panel information hierarchy, module row spacing, active state, lesson-position context, and alignment while preserving real data.
5. **Fix content/quiz rhythm second.** Harmonize typography, margins, choice affordances and pager placement; test the quiz's selected, feedback, saving and completed states.
6. **Browser-verify each meaningful change** and take before/after screenshots. Do not mark a visual milestone done based only on passing pytest/Node checks.
7. **Integrate the mentor orb separately**, after the lesson view is stable, and verify it does not cover reading or action controls.

## Minimum acceptance criteria

- Exactly one visible lesson title and one breadcrumb.
- No redundant path-selector card while reading.
- Sidebar matches approved hierarchy and has accurate real completion states; active module and lesson are visible upon resume.
- Lesson metadata, title, content, quiz and pager form the same overall composition as Prototype A at matched viewport/zoom.
- No hard-coded demo content or fabricated scores/lesson counts.
- Quiz, incomplete-attempt behavior, SQLite persistence, Previous/Next, Continue Learning and automatic resume continue to work.
- The work is visually approved against **actual browser screenshots**; automated test success alone is not visual approval.

## Status

**Status: Deferred. Target: Post-v0.2.0. Candidate milestone: v0.2.1 (not yet scheduled).**

This document records observations and recommendations only. It does **not** assert that the checked-in source has been changed or that a v0.2.1 milestone has been scheduled. Do not delete or overwrite the existing uncommitted `dev` work based on this note.
