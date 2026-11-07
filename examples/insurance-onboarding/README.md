# Insurance onboarding comparison

Two named crews receive exactly `prompt.txt` in separate empty application chats. It contains a short fictional motor-insurance brief and asks for a three-page illustrated onboarding PDF in English. All configured names, instructions and expected outputs are English.

The Basic Crew has a general coordinator and writer, calculator/PDF permissions, and a runtime-enforced disabled skill policy. The Equipped Crew has a coordinator, content writer, illustrator, quality reviewer and editorial/PDF publisher; it can create original images and use the registered magazine-layout skill. Both crews default to the same model; choose the same actually available model for both on the target installation. This compares complete team configurations, not an isolated causal test of one skill.

Instructions guide each agent's responsibility; there is no code-defined stage sequence. The manager chooses delegation and revisions based on the available members and actual replies. `skillsEnabled: false` filters assigned and discoverable skills only for that execution, without changing the shared registry or the other crew.

Merge the portable agents/teams into an installation's existing state, preserving its other teams, credentials and history. Keep generated chats, execution evidence and files in that installation's runtime data. No real insurance terms, personal data, server addresses or credentials belong in this example.

For a fair demonstration, retain both raw PDFs, input hashes, empty-chat identities, provider-reported usage, elapsed time, actual delegations, skill-selection/application events and artifact counts. Verify readability and content by rendering all PDF pages. Never manufacture a failed baseline or manually redesign a claimed agent-generated output. A textual/metadata check alone is not visual inspection. Real inference requires the installation's own connected text account and an independent connected native image session.
