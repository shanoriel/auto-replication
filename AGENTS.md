# AutoReplication Working Notes

## UI Change Discipline

- You may change implementation architecture, file structure, and internal state management as needed.
- You must not change the existing layout, interaction flow, or functional definition of an established page unless the user explicitly asks for that product/UI change.
- When adding a new page or mode, preserve the current page behavior as-is and layer the new capability in with minimal surface-area impact.
- If a design implementation requires touching an existing page, first treat the current UI as a compatibility contract, not as a draft to redesign.
