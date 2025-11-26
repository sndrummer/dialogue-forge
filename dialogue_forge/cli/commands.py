"""
CLI commands for dialogue forge
"""

import click
from pathlib import Path
from dialogue_forge.parser.parser import DialogueParser


@click.group()
def cli():
    """Dialogue Forge - A dialogue authoring tool for Avatar: The Ashen Path"""
    pass


@cli.command()
@click.argument('file_path', type=click.Path(exists=True))
@click.option('--detailed', '-d', is_flag=True, help='Show detailed validation output')
def validate(file_path, detailed):
    """Validate a .dlg dialogue file"""
    path = Path(file_path)
    parser = DialogueParser()

    try:
        dialogue = parser.parse_file(path)
        is_valid = parser.validate()
        stats = parser.get_stats()

        click.echo(f"\n📄 File: {path.name}")
        click.echo("-" * 40)

        # Basic stats
        click.echo(f"Characters: {stats['characters']}")
        click.echo(f"Nodes: {stats['nodes']}")
        click.echo(f"Dialogue lines: {stats['dialogue_lines']}")
        click.echo(f"Choices: {stats['choices']}")
        click.echo(f"Commands: {stats['commands']}")

        if detailed:
            click.echo("\n📊 Detailed Analysis:")
            click.echo("-" * 40)

            # Show characters
            click.echo("\nCharacters:")
            for char_id, display_name in dialogue.characters.items():
                click.echo(f"  • {char_id}: {display_name}")

            # Show sample nodes
            click.echo("\nSample Nodes:")
            for i, (node_id, node) in enumerate(dialogue.nodes.items()):
                if i >= 3:
                    break
                click.echo(f"  [{node_id}] - {len(node.lines)} lines, {len(node.choices)} choices")

        # Validation results
        if dialogue.errors:
            click.echo("\n❌ Errors:")
            for error in dialogue.errors:
                click.echo(f"  • {error}", err=True)

        if dialogue.warnings:
            click.echo("\n⚠️  Warnings:")
            for warning in dialogue.warnings:
                click.echo(f"  • {warning}")

        if is_valid and not dialogue.errors:
            click.echo("\n✅ Validation passed!")
        else:
            click.echo("\n❌ Validation failed!", err=True)
            raise click.Exit(1)

    except Exception as e:
        click.echo(f"\n❌ Error: {e}", err=True)
        raise click.Exit(1)


@cli.command()
@click.argument('file_path', type=click.Path(exists=True))
def stats(file_path):
    """Show statistics for a .dlg dialogue file"""
    path = Path(file_path)
    parser = DialogueParser()

    try:
        dialogue = parser.parse_file(path)
        stats = parser.get_stats()

        click.echo(f"\n📊 Statistics for {path.name}")
        click.echo("=" * 50)

        click.echo(f"\n📝 Content:")
        click.echo(f"  Characters:     {stats['characters']:>6}")
        click.echo(f"  Nodes:          {stats['nodes']:>6}")
        click.echo(f"  Dialogue lines: {stats['dialogue_lines']:>6}")
        click.echo(f"  Choices:        {stats['choices']:>6}")
        click.echo(f"  Commands:       {stats['commands']:>6}")

        # Calculate some derived stats
        avg_choices = stats['choices'] / stats['nodes'] if stats['nodes'] > 0 else 0
        avg_lines = stats['dialogue_lines'] / stats['nodes'] if stats['nodes'] > 0 else 0

        click.echo(f"\n📈 Averages:")
        click.echo(f"  Choices per node: {avg_choices:>6.1f}")
        click.echo(f"  Lines per node:   {avg_lines:>6.1f}")

        # Find branching complexity
        branching_nodes = sum(1 for node in dialogue.nodes.values() if len(node.choices) > 1)
        linear_nodes = sum(1 for node in dialogue.nodes.values() if len(node.choices) == 1)
        dead_ends = sum(1 for node in dialogue.nodes.values() if len(node.choices) == 0)

        click.echo(f"\n🌳 Structure:")
        click.echo(f"  Branching nodes: {branching_nodes:>6}")
        click.echo(f"  Linear nodes:    {linear_nodes:>6}")
        click.echo(f"  Dead ends:       {dead_ends:>6}")

        if stats['errors'] > 0 or stats['warnings'] > 0:
            click.echo(f"\n⚠️  Issues:")
            click.echo(f"  Errors:   {stats['errors']:>6}")
            click.echo(f"  Warnings: {stats['warnings']:>6}")

        click.echo()

    except Exception as e:
        click.echo(f"\n❌ Error: {e}", err=True)
        raise click.Exit(1)


@cli.command()
@click.argument('file_path', type=click.Path(exists=True))
@click.argument('node_id')
def show_node(file_path, node_id):
    """Display a specific node from a dialogue file"""
    path = Path(file_path)
    parser = DialogueParser()

    try:
        dialogue = parser.parse_file(path)

        if node_id not in dialogue.nodes:
            click.echo(f"❌ Node '{node_id}' not found in {path.name}", err=True)
            click.echo("\nAvailable nodes:")
            for nid in sorted(dialogue.nodes.keys())[:20]:
                click.echo(f"  • {nid}")
            if len(dialogue.nodes) > 20:
                click.echo(f"  ... and {len(dialogue.nodes) - 20} more")
            raise click.Exit(1)

        node = dialogue.nodes[node_id]

        click.echo(f"\n📍 Node: [{node_id}]")
        click.echo("=" * 50)

        # Show commands
        if node.commands:
            click.echo("\n⚡ Commands:")
            for cmd in node.commands:
                click.echo(f"  *{cmd}")

        # Show dialogue
        if node.lines:
            click.echo("\n💬 Dialogue:")
            for speaker, text in node.lines:
                click.echo(f"  {speaker}: \"{text}\"")

        # Show choices
        if node.choices:
            click.echo("\n🔀 Choices:")
            for choice in node.choices:
                cond_str = f" {{{choice.condition}}}" if choice.condition else ""
                if choice.text:
                    click.echo(f"  -> {choice.target}: \"{choice.text}\"{cond_str}")
                else:
                    click.echo(f"  -> {choice.target}{cond_str}")

        click.echo()

    except Exception as e:
        click.echo(f"\n❌ Error: {e}", err=True)
        raise click.Exit(1)


if __name__ == '__main__':
    cli()