---
name: magazine-layout
description: >
  Design visually rich magazines, children's picture books and premium editorial PDFs. Choose the visual direction,
  typography, page composition, image crops, hierarchy and pacing from the content and audience, using 12 magazine styles.
  Use for requests where the document should look designed rather than like a default report.
license: MIT
metadata:
  requires: [pdf-generator]
  source: https://github.com/isjiamu/jiamu-skills/tree/3c213712723a099ffff136011b51f9a1ca5b708f/magazine-layout
---
# Magazine Layout — autonomous editorial design

Adapted from isjiamu/jiamu-skills magazine-layout (MIT). Original instructions and all 12 style references are retained under skills/magazine-layout/upstream. The adapted guidance is self-contained; the original full reference remains available in the retained source files. This is an integration of a community skill, not an external certification.

## Make the design decisions

Understand the content, audience and requested page count. Select and combine an appropriate visual direction from the 12 styles below. The user delegates editorial choices by default: choose the layout, color, typography, cover treatment and pacing yourself; do not ask them to pick fonts or grids unless they explicitly want to. Preserve user-supplied material according to the brief; newly generated proposals may be edited when storytelling/design decisions are delegated. Do not invent factual sources or use unlicensed remote assets. Do not enforce a fixed agent workflow.

## Match the publication to the brief

First distinguish a magazine/article from a children's picture book. The twelve magazine references below are a vocabulary of visual techniques, not a template to apply to every publication. A picture-book request needs visual storytelling and page turns, rather than the appearance of a business report with an illustration inserted above body copy.

### Children's picture books

A separately requested cover is its own designed page: a strong original illustration and the book title, with optional brief credit/subtitle when appropriate. Begin the narrative on the interior pages, not on the cover. Count the cover according to the user's brief: “a cover plus two story pages” means three pages; an explicitly stated total remains the total. Do not silently merge the cover with the opening story to save a page.

Let illustrations carry the setting, emotion and action. Choose a book trim and page compositions that suit the art and reader. Art should feel integrated into the page, often full-page, edge-to-edge or generously scaled with intentional space for the words. Plan the text zones and title space when commissioning illustrations. Keep important characters and actions visible when cropping. Avoid shrinking portrait art into the center of a wide dark rectangle or adding empty side bars simply to fill a mismatched frame. If the art and layout do not fit, change the composition rather than disguising the mismatch.

Use concise, read-aloud storytelling and deliberate page turns. Fit the writing to an illustration-led experience; do not fill a tiny page allowance with a long manuscript and then shrink the art or type. Preserve user-supplied or user-approved wording unless the brief authorizes editorial rewriting. For a new story with delegated creative decisions, adapt the draft length to the picture-book experience while retaining its coherent plot and resolution. A teammate’s proposed manuscript or layout is not an irrevocable user approval. If a material revision needs another agent, explain the concrete revision to the manager instead of publishing an unsuitable layout. Choose one coherent visual language across the cover and interiors, while giving each interior scene a distinct action and composition.

Choose readable, usually regular-weight body type; reserve bold/display typography for actual emphasis or titles. Establish contrast and scale from the mood and audience. Report boxes, routine repeated headers, corporate mastheads, decorative rules, obligatory two-column paragraphs and pull quotes are not default picture-book devices. Use them only when they genuinely serve the chosen book concept. Whitespace should support pacing and art, not result from a small image and a text block stranded in one corner.

Treat another agent's layout recommendation as a proposal to reconcile with the requested medium and this design guidance, unless the user explicitly approved a fixed layout. Respect actual user approvals while improving image scale, typography, page balance and cover treatment. The skill guides judgment; it does not prescribe a fixed palette, font pairing, grid, orientation or sequence of agents.

For magazine/article requests, select and combine a fitting direction from the upstream styles below. For picture books, borrow only techniques that serve the story rather than reproducing a magazine/report template.

## Use the real PDF tool

1. Call use_skill with skill_id magazine-layout and a short public reason when this skill fits.
2. Read supplied story/artifacts as needed. Use read_generated_file to recover prior generated sources. Plan your editorial composition before rendering. Keep that plan concise and public, never hidden chain of thought.
3. Author your own complete self-contained HTML with inline CSS and call the existing pdf_generator tool. Its request argument is a JSON string with layout set to editorial-html, html containing the complete designed document, and page_count set to the agreed total number of pages. Choose the CSS page size and geometry yourself; the tool does not impose a book trim or layout.
Supply the exact PNG artifact URLs used in img src or CSS background-image through reference_urls. Only conversation-owned generated PNG URLs and the bundled fonts can be fetched. Do not pass local file paths, external image URLs, data URLs or placeholder asset URLs. If no images are available, design honestly for text only or explain a required illustration capability.

You control all HTML/CSS geometry; the renderer does not supply a fixed cover or article template. Plan within the page area, keep text readable, and reserve enough height for the actual word count. Create one explicit page element for each intended page, with appropriate page breaks and no trailing blank page; set page_count to that agreed total. Account for padding and image heights, use box-sizing:border-box. Do not hide overflow to conceal excess text: verify all narrative after rendering and fix any loss.

The engine is offline WeasyPrint, not a browser running JavaScript. Write full CSS directly; do NOT rely on Tailwind's CDN/script, Google Fonts imports, external stylesheets, scripts or canvas. Use CSS flex/grid, floats, columns, absolute placement, object-fit or backgrounds as appropriate. Include a font family fallback. The upstream references include Tailwind examples; translate those utility classes into inline stylesheet rules rather than loading Tailwind.

Rendering reliability: place image-overlay titles INSIDE the same position:relative hero element so bottom/left coordinates refer to that image, not to the entire page. Give every text block strong contrast against its actual background. Avoid CSS floated :first-letter drop caps in this engine because they can overlap the first line; choose normal typography or an explicit inline initial instead. Preserve user-approved wording when rewriting is not authorized; maintain coherent narrative and dialogue order. Pull quotes are optional repetitions, never replacements that move a reply before its question. Keep all narrative and display titles visibly inside their intended frames.

Bundled licensed fonts: EditorialDisplay (DM Serif Display) for expressive display headings; EditorialText (DM Sans, variable weights) for body, labels and supporting text. These fonts are embedded offline. You can use serif/sans-serif fallbacks; never pretend unsupported external fonts loaded. Image backgrounds and cropped frames are allowed when no essential scene information is lost.

4. Set the tool's title to your chosen document title. Use a coherent typographic hierarchy and appropriate credits. Add folios only if they suit the publication; a picture-book cover does not need a visible page number. Reader-facing pages must not mention the model, skill, renderer, AgentSim or technical implementation unless requested.
If the tool rejects malformed JSON, correct the escaping or missing closing braces and retry the SAME designed HTML/CSS. Do not silently replace the selected editorial composition with a plain pages/chapters template. This is a generic rendering tool: all editorial choices remain yours, guided by this skill.

5. Call read_generated_file on the real result. Verify page count, full narrative, headings and image count. A metadata/text read is not a visual inspection. If the tool rejects the page count or the source text is missing, revise your HTML and render again. Return a real PDF link, not HTML or a promise. Do not claim PDF/X, CMYK/ICC/bleed compliance without a separate preflight.

## Magazine directions (use only when appropriate to the medium)

The original twelve-style reference and HTML/CSS examples are preserved in upstream/styles.md. The adapted decision guide below is self-contained; writing a new composition does not require copying those browser templates.

| Direction | Useful design character |
| --- | --- |
| Classic Elegance | Expressive serif hierarchy, restrained color, spacious rhythm. |
| Modern Minimalist | Precise alignment, calm hierarchy, purposeful negative space. |
| Tech Magazine | Structured technical hierarchy, diagrams and crisp contrast. |
| Nature & Lifestyle | Organic image-led storytelling, tactile warmth, natural color. |
| Bold Editorial | Decisive image scale, expressive headlines and energetic asymmetry. |
| Vintage Retro | Historically coherent type, paper texture and deliberate period references. |
| Corporate Professional | Clear business information and restrained, consistent hierarchy. |
| Creative Art | Content-led experimentation and expressive visual relationships. |
| Academic Journal | Long-form readability, evidence hierarchy and disciplined references. |
| Fashion Luxe | Strong art direction, elegant image scale and selective typography. |
| News & Report | Rapid scanning, headlines and dense information organization. |
| Dark Mode Tech | Technical information with controlled dark/light contrast. |

These are possible directions, not mandatory components or fixed palettes. A children's picture book should follow the illustration-led guidance above rather than reproduce a corporate, academic or magazine layout simply because those references exist.
