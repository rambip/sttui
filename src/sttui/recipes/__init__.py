"""sttui recipes."""

from pathlib import Path

RECIPE_DIR = Path(__file__).parent


def list_recipes() -> list[str]:
    """Return list of available recipe names."""
    return [p.stem for p in RECIPE_DIR.glob("*.md")]


def load_recipe(name: str) -> str:
    """Load a recipe markdown file by name."""
    recipe_path = RECIPE_DIR / f"{name}.md"
    if recipe_path.exists():
        return recipe_path.read_text(encoding="utf-8")
    raise FileNotFoundError(f"Recipe not found: {name}")


def get_index_markdown() -> str:
    """Generate the recipes index markdown."""
    recipes = list_recipes()
    
    agents_md = """\
# sttui recipes

Practical recipes organized by context.

## Available chapters
"""
    for recipe in sorted(recipes):
        if recipe == "desktop":
            desc = "Desktop environment keybinding setup (GNOME, KDE, Hyprland, ...)"
        elif recipe == "agents":
            desc = "Integrate sttui with AI coding agents (opencode, pi)"
        else:
            desc = recipe
        
        agents_md += f"- **{recipe}** — {desc}\n"
    
    agents_md += "\nRun `sttui recipes <chapter>` to read one.\n"
    return agents_md