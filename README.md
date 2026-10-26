# Production tree

A small local tool to draw machines as blocks, give them inputs and outputs (items, fluids, FE), connect them together and arrange them on a board.

It runs on your computer: a tiny Python server plus one HTML page. No install needed, only Python 3 (standard library).

## Quick start

1. Put all the files in one folder (see below).
2. Run `python server.py`.
3. Your browser opens `http://localhost:8000` (the server tries ports 8000 to 8010).

Do not open `index.html` by double-click: it needs the server to read and save files. Press `Ctrl+C` in the terminal to stop the server.

## Why `server.py` is required

`server.py` is **mandatory**: the app does not work without it. A web page cannot read or write files on your computer by itself, so the server does that job for it. It lists your images, loads and saves blocks, UI models, connections and positions, and serves the page. Without it you will only see a message asking you to start the server.

### Is it safe for my data?

Yes, it is not a threat to your data:

- It is a single, short, readable Python file. You can open it in any text editor and check it.
- It uses only Python's standard library: nothing to install, no extra packages.
- It listens on `127.0.0.1` only, so it is reachable from your own computer and not from other devices on your network.
- It never connects to the internet and sends nothing anywhere.
- It only works inside its own folder, and it only creates or changes `.json` files there (blocks, `ui_models/`, `connections.json`, `layout.json`). Your images are only read, never modified.
- It refuses to serve `.py` and `.bat` files through the browser.

As with any program, only run a copy you got from a source you trust.

## Folder structure

```
production-tree/
├── server.py            the local server (run this)
├── index.html           the whole interface
├── machinery_blocks/    your images (.png .jpg .jpeg .gif .webp .svg)
├── ui_models/           saved UI models, one .json each   (created automatically)
├── iron_furnace.json    one file per block                (created automatically)
├── connections.json     lines between blocks              (created automatically)
└── layout.json          position of each block            (created automatically)
```

- **`machinery_blocks/`** is the only folder you fill by hand. Every image in it can be used as a block icon or as the picture of a slot.
- **`ui_models/`** holds the "frames" of your machines (see below).
- **Block files** live in the main folder, next to `server.py`. Any `.json` there with a `name` field is shown as a block. `connections.json` and `layout.json` have no `name`, so they are ignored as blocks.
- File names come from the name you type: lowercase, no accents, spaces become `_`. If the name already exists, `_2`, `_3`, ... is added.

## The `.json` files: you don't have to touch them

Everything can be done from the web page. The `.json` files are just where the page saves its work, so **editing them by hand is optional**.

Open them only when you want absolute control over a UI, for example:

- exact pixel positions (the editor snaps to a 4 px grid, a file does not have to);
- pieces that touch or overlap (the editor refuses overlaps, the file reader does not);
- quick bulk edits, such as renaming things or changing many amounts at once.

The page re-reads the files every 2 seconds, so a saved edit shows up by itself.

Hand-edited files are read in a forgiving way: numbers outside the allowed range are clamped, unknown pieces are skipped, and `side` is always recalculated from `x`. A typo will not crash the server. Strict checks only apply when you save from the page.

### UI model (`ui_models/furnace.json`)

A UI model is the frame of a machine: where the slots, arrow and other pieces are.

```json
{
  "name": "Furnace",
  "width": 240,
  "height": 120,
  "defaultArrow": true,
  "pieces": [
    { "type": "item",  "x": 16,  "y": 40, "side": "input",  "active": true },
    { "type": "flame", "x": 106, "y": 12, "level": 75 },
    { "type": "item",  "x": 188, "y": 40, "side": "output", "active": true }
  ]
}
```

| Piece | Size (px) | Extra fields |
|-------|-----------|--------------|
| `item` | 36 x 36 | slot |
| `fluid` | 24 x 104 | slot |
| `energy` (FE) | 24 x 104 | slot |
| `button` | 24 high, 40 to 160 wide | `text` (1 to 20 chars), `w` |
| `arrow` | 44 x 32 | `progress` 0 to 100 |
| `flame` | 28 x 32 | `level` 0 to 100 |

Rules: UI width 120 to 420, height 40 to 240, up to 32 pieces. `item`, `fluid` and `energy` are the **slots**. The left half of the UI is inputs, the right half is outputs. `active: true` means the slot gets a connection square on the block. The **order of the slots** in `pieces` is their slot number.

### Block (`furnace_1.json`)

A block is a UI model filled with real content.

```json
{
  "name": "Furnace",
  "icon": "machinery_blocks/furnace.png",
  "width": 276,
  "height": 198,
  "ui": "furnace",
  "content": [
    { "name": "Iron_Ore",   "amount": 1, "icon": "machinery_blocks/iron_ore.png" },
    { "name": "Iron_Ingot", "amount": 1, "icon": null }
  ]
}
```

- `ui` is the file name of the UI model without `.json`.
- `content` has **one entry per slot**, in slot order: entry 1 fills the first slot, and so on.
- Block size: width 160 to 480, height 64 to 320.

### Other files

- `connections.json`: `{"links": [{"from": {"block": "a.json", "slot": 1}, "to": {"block": "b.json", "slot": 0}}]}`. The slot number starts from 0 and counts all slots, active or not.
- `layout.json`: `{"pos": {"a.json": {"x": 120, "y": 44}}}`, the position of each block on the board.

Deleting a block: delete its `.json` file. Its lines disappear from the board but stay in `connections.json` until you remove them.

## How to create a UI

Press **Create UI**.

1. Type a **name** and set the **width and height** of the frame.
2. Keep or remove the **default arrow** in the middle.
3. **Drag pieces** from the palette onto the canvas (or just click a piece to place it in the first free spot).
4. **Click a piece** to edit it: slot number, active on or off, button text and width, arrow progress, flame level.
5. Move a piece by dragging it (or with the arrow keys). Drag it off the canvas, or press `Delete`, to remove it.
6. Press **Save UI**. It is saved in `ui_models/`.

Tips: pieces on the left half are inputs, on the right half are outputs. The small numbers on the slots are the slot numbers, and a green number means the slot is active.

## How to create a block

Press **Create block**.

1. Type the **name** of the block.
2. Optionally pick an **icon** from `machinery_blocks/`.
3. Choose a **UI model**. A preview appears.
4. For each slot, fill in the **name**, the **amount** and an optional **image**. Item slots show the image (or the first letter of the name), fluid and FE slots tile the image inside the column.
5. The **size** is filled in from the UI model. You can change it.
6. Press **Create**. A new `.json` file appears in the main folder.

## Connections and moving blocks

- **Connect:** drag from a square on the right edge (output) to a square on the left edge (input) of another block. Only the same type can be connected: item to item, fluid to fluid, FE to FE. Compatible squares light up in yellow while you drag.
- **Remove a connection:** click its line.
- **Move a block:** drag it by its body (not by the squares). The position is saved in `layout.json`.
- Square colors: gray = item, blue = fluid, red = FE.

## I'll work as much as i can, wish me luck!



![Production tree screenshot](working_hard.jpg)
