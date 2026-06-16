#!/usr/bin/env python3
"""
sync.py — Synchronise les dossiers de séquences avec le site.

Usage :
    python3 sync.py

Fonctionnement :
  1. Lit ressources.json (local)
  2. Pour chaque dossier pdf/seq-{id}/ détecte les nouveaux PDFs
  3. Les enregistre dans ressources.json (catégorie connaissance)
  4. Génère les miniatures via qlmanage (macOS)
  5. Git commit + push vers GitHub Pages
"""
import os, json, subprocess, re, unicodedata, shutil, sys

REPO      = os.path.dirname(os.path.abspath(__file__))
JSON_PATH = os.path.join(REPO, 'ressources.json')
THUMB_DIR = os.path.join(REPO, 'img', 'thumbs')
SSH_KEY   = os.path.expanduser('~/.ssh/github_techno')


# ── Utilitaires ──────────────────────────────────────────────────────────────

def nfc(s):
    return unicodedata.normalize('NFC', s)

def title_from_filename(name):
    name = os.path.splitext(name)[0]
    name = name.replace('-', ' ').replace('_', ' ')
    name = re.sub(r'\s+', ' ', name).strip()
    return name[:1].upper() + name[1:] if name else name

def find_thumb(base, thumb_dir):
    """Cherche le .png généré par qlmanage (gère NFD/NFC, suffixe 001, et .pdf.png)."""
    candidates = [f'{base}{s}.png' for s in ('', '001')] + \
                 [f'{base}.pdf{s}.png' for s in ('', '001')]
    for candidate in candidates:
        for f in os.listdir(thumb_dir):
            if nfc(f) == nfc(candidate):
                return os.path.join(thumb_dir, f)
    return None

def generate_thumb(pdf_path, res_id, thumb_dir):
    try:
        subprocess.run(
            ['qlmanage', '-t', '-s', '400', '-o', thumb_dir, pdf_path],
            capture_output=True, timeout=30
        )
        base = os.path.splitext(os.path.basename(pdf_path))[0]
        src  = find_thumb(base, thumb_dir)
        if src:
            dst = os.path.join(thumb_dir, f'thumb-{res_id}.png')
            shutil.move(src, dst)
            return True
    except Exception as e:
        print(f'    ! Miniature : {e}')
    return False


# ── Scan ─────────────────────────────────────────────────────────────────────

def main():
    print('── Sync séquences ──────────────────────────────')

    with open(JSON_PATH, encoding='utf-8') as f:
        data = json.load(f)

    resources = data['resources']
    next_id   = data['nextId']

    seqs         = {r['id']: r for r in resources if r.get('type') == 'sequence'}
    existing_urls = {r.get('url', '') for r in resources}
    added = []

    for seq_id, seq in sorted(seqs.items()):
        folder = os.path.join(REPO, 'pdf', f'seq-{seq_id}')
        os.makedirs(folder, exist_ok=True)

        files = sorted(
            f for f in os.listdir(folder)
            if f.lower().endswith('.pdf') and not f.startswith('.')
        )

        for filename in files:
            rel_url = f'pdf/seq-{seq_id}/{filename}'
            if rel_url in existing_urls:
                continue

            res_id  = next_id
            next_id += 1
            titre   = title_from_filename(filename)

            new_res = {
                'id'        : res_id,
                'titre'     : titre,
                'desc'      : f'Ressource — Séq. {seq.get("seq_num","")} {seq["titre"]}.',
                'type'      : 'document',
                'categorie' : 'connaissance',
                'niveau'    : seq['niveau'],
                'parent_seq': seq_id,
                'url'       : rel_url,
            }
            resources.append(new_res)
            existing_urls.add(rel_url)
            added.append((res_id, rel_url))
            print(f'  + ID {res_id} : {rel_url}')

            pdf_full = os.path.join(REPO, rel_url)
            ok = generate_thumb(pdf_full, res_id, THUMB_DIR)
            print(f'    {"→" if ok else "! pas de"} miniature thumb-{res_id}.png')

    if not added:
        print('  Aucun nouveau fichier détecté.')

    data['nextId'] = next_id

    with open(JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f'  ressources.json mis à jour ({next_id - data["nextId"] + len(added)} entrées)')

    # ── Git ──────────────────────────────────────────────────────────────────
    os.chdir(REPO)

    subprocess.run(['git', 'add', 'ressources.json', 'img/thumbs/'] +
                   [f'pdf/seq-{sid}/' for sid in seqs], check=True)

    diff = subprocess.run(['git', 'diff', '--cached', '--quiet'])
    if diff.returncode == 0:
        print('\nAucune modification à publier.')
        return

    n   = len(added)
    msg = f'Sync : {n} nouveau(x) fichier(s)' if n else 'Sync séquences (structure)'
    subprocess.run(['git', 'commit', '-m', msg], check=True)

    env = os.environ.copy()
    if os.path.exists(SSH_KEY):
        env['GIT_SSH_COMMAND'] = f'ssh -i {SSH_KEY}'
    subprocess.run(['git', 'push'], env=env, check=True)

    print(f'\n✅ Site synchronisé — {n} fichier(s) ajouté(s).')
    print('   Le site sera à jour dans ~1 minute.')


if __name__ == '__main__':
    main()
