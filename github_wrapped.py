import requests
import sys
import time
from collections import defaultdict
from rich.console import Console
from rich.panel import Panel
from rich.text import Text
from rich.table import Table
from rich import box

console = Console()


# ── API helpers ────────────────────────────────────────────────────────────────

def make_headers(token):
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
    }


def get_user_info(username, headers):
    r = requests.get(f"https://api.github.com/users/{username}", headers=headers)
    r.raise_for_status()
    return r.json()


def get_all_repos(username, headers):
    """Fetch every repo owned by the user (handles pagination)."""
    repos, page = [], 1
    while True:
        r = requests.get(
            f"https://api.github.com/users/{username}/repos",
            headers=headers,
            params={"per_page": 100, "page": page, "type": "owner"},
        )
        r.raise_for_status()
        data = r.json()
        if not data:
            break
        repos.extend(data)
        page += 1
    return repos


def get_commit_count(username, year, headers):
    """Total commits authored in the given year using the search API."""
    search_headers = {**headers, "Accept": "application/vnd.github.cloak-preview"}
    r = requests.get(
        "https://api.github.com/search/commits",
        headers=search_headers,
        params={
            "q": f"author:{username} committer-date:{year}-01-01..{year}-12-31",
            "per_page": 1,
        },
    )
    if r.status_code == 200:
        return r.json().get("total_count", 0)
    return None  # graceful fallback if search isn't available


def get_pr_count(username, year, headers):
    """Total PRs opened in the given year."""
    r = requests.get(
        "https://api.github.com/search/issues",
        headers=headers,
        params={
            "q": f"author:{username} type:pr created:{year}-01-01..{year}-12-31",
            "per_page": 1,
        },
    )
    if r.status_code == 200:
        return r.json().get("total_count", 0)
    return None


def get_languages(username, repos, headers):
    """Aggregate language byte counts across all non-fork repos."""
    lang_bytes = defaultdict(int)
    for repo in repos:
        if repo["fork"]:
            continue  # skip forks — we only want your own code
        r = requests.get(
            f"https://api.github.com/repos/{username}/{repo['name']}/languages",
            headers=headers,
        )
        if r.status_code == 200:
            for lang, count in r.json().items():
                lang_bytes[lang] += count
        time.sleep(0.05)  # stay friendly to the API rate limit
    return dict(sorted(lang_bytes.items(), key=lambda x: x[1], reverse=True))


# ── Display ────────────────────────────────────────────────────────────────────

def display_wrapped(user, year, commit_count, pr_count, repos, languages):
    console.clear()
    console.print()

    # ── Title card
    title = Text(f"✦  GitHub Wrapped {year}  ✦", justify="center")
    title.stylize("bold magenta")
    console.print(Panel(title, border_style="magenta", padding=(1, 6)))
    console.print()

    name = user.get("name") or user.get("login")
    console.print(f"  Hey [bold cyan]{name}[/bold cyan] 👋  Here's your year in code.\n")

    # ── Commits
    if commit_count is not None:
        flavor = (
            "You basically lived in the terminal. 🏠"
            if commit_count > 1000
            else "Solid year of shipping. 💪"
            if commit_count > 300
            else "Quality over quantity. 🎯"
        )
        console.print(Panel(
            f"[bold yellow]🔥  {commit_count:,} commits[/bold yellow]\n[dim]{flavor}[/dim]",
            title="[bold]Commits[/bold]",
            border_style="yellow",
            padding=(0, 2),
        ))
        console.print()

    # ── Pull Requests
    if pr_count is not None:
        flavor = (
            "Reviewing machine. 🤖" if pr_count > 200
            else "Great collaborator. 🤝" if pr_count > 50
            else "Thoughtful contributor. 🧠"
        )
        console.print(Panel(
            f"[bold green]🔀  {pr_count:,} pull requests[/bold green]\n[dim]{flavor}[/dim]",
            title="[bold]Pull Requests[/bold]",
            border_style="green",
            padding=(0, 2),
        ))
        console.print()

    # ── Top repos by stars
    total_stars = sum(r["stargazers_count"] for r in repos)
    top_repos = sorted(repos, key=lambda r: r["stargazers_count"], reverse=True)[:5]

    star_table = Table(box=box.SIMPLE, show_header=True, header_style="bold blue", padding=(0, 1))
    star_table.add_column("Repo", style="cyan", no_wrap=True)
    star_table.add_column("⭐", justify="right", style="yellow")
    star_table.add_column("Description", style="dim")

    for repo in top_repos:
        desc = (repo["description"] or "")[:55]
        star_table.add_row(repo["name"], str(repo["stargazers_count"]), desc)

    console.print(Panel(
        star_table,
        title=f"[bold]⭐  Stars  [dim](lifetime total: {total_stars:,})[/dim][/bold]",
        border_style="blue",
    ))
    console.print()

    # ── Languages
    if languages:
        total_bytes = sum(languages.values())
        top_langs = list(languages.items())[:6]

        lang_text = Text()
        for lang, count in top_langs:
            pct = count / total_bytes * 100
            bar = "█" * int(pct / 2.5)
            lang_text.append(f"\n  {lang:<22}", style="bold cyan")
            lang_text.append(bar, style="magenta")
            lang_text.append(f"  {pct:.1f}%", style="dim")
        lang_text.append("\n")

        console.print(Panel(
            lang_text,
            title="[bold]💻  Languages[/bold]",
            border_style="cyan",
        ))
        console.print()

    # ── Sign-off
    top_lang = list(languages.keys())[0] if languages else "code"
    console.print(
        f"  [dim]Your go-to language was [bold white]{top_lang}[/bold white]. "
        f"Keep shipping in {int(year) + 1}! 🚀[/dim]\n"
    )


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    # Use plain input() for better compatibility across terminals
    print("\n🐙 GitHub Wrapped — Let's see what you built!\n")

    username = input("GitHub username: ").strip()
    token    = input("Personal access token: ").strip()
    year     = input("Year (e.g. 2024): ").strip()

    if not year.isdigit() or len(year) != 4:
        console.print("[red]❌  Invalid year. Please enter a 4-digit year like 2024.[/red]")
        sys.exit(1)

    headers = make_headers(token)

    # Validate credentials
    with console.status("[bold green]Connecting to GitHub...[/bold green]"):
        try:
            user = get_user_info(username, headers)
        except requests.HTTPError:
            console.print("[red]❌  Could not authenticate. Double-check your username and token.[/red]")
            sys.exit(1)

    with console.status("[bold green]Fetching repos, commits & PRs...[/bold green]"):
        repos        = get_all_repos(username, headers)
        commit_count = get_commit_count(username, year, headers)
        pr_count     = get_pr_count(username, year, headers)

    with console.status(f"[bold green]Crunching language stats across {len(repos)} repos...[/bold green]"):
        languages = get_languages(username, repos, headers)

    display_wrapped(user, year, commit_count, pr_count, repos, languages)


if __name__ == "__main__":
    main()
