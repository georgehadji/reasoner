# Context: Ui

## Directory: `ui-next/src/components/ui`

## Description
Atomic, unstyled design components (buttons, dialogs, inputs, cards) constructed with Radix/Shadcn UI.

## Files
- **`Badge.tsx`**: Code or resource asset facilitating system functionality.
- **`LogoLoop.tsx`**: Infinite horizontal marquee of arbitrary nodes, adapted from React Bits. Measures one sequence, duplicates it to cover the container, and advances a single `translate3d` with an eased velocity. Parked off-screen and in a backgrounded tab; renders a static wrapped list under `prefers-reduced-motion`. Used for the provider strip in the landing masthead.
- **`SpotlightCard.tsx`**: Accent wash that follows the cursor, adapted from React Bits. Renders the overlay only — the caller owns border, background and padding — at a negative z-index inside an isolated root so it paints under the card's own content. Mouse-only, and absent entirely under `prefers-reduced-motion`. Used for the pricing tiers.
- **`Button.tsx`**: Button Variant Styles --------------------------------------------------------------------------
- **`ProfessionalRenderer.tsx`**: Helper to check for hex color validity
- **`Spinner.tsx`**: Code or resource asset facilitating system functionality.
- **`ThemeToggle.tsx`**: Mount-gated: `resolvedTheme` is undefined server-side, so deriving the
- **`Tooltip.tsx`**: Hover/focus tooltip.  The wrapper is focusable and the bubble is wired up with `aria-describedby`
- **`index.ts`**: Code or resource asset facilitating system functionality.

## Subfolders
*No subfolders in this directory.*
