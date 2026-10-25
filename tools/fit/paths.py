"""Where the published assets live (site/assets/)."""
import os, re

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'site', 'assets') + os.sep
GARMENTS = ASSETS + 'garments' + os.sep   # NNN.glb, one per piece
BODY = ASSETS + 'body' + os.sep           # pose-b.glb, pose-c.glb and poses.json
MASKS = ASSETS + 'masks' + os.sep         # pose-b/NNN.json, pose-c/NNN.json: body triangles hidden under each piece
LAYERS = ASSETS + 'layers' + os.sep       # NNN.json: top-over-bottom tables, one per bottom
PHOTOS = ASSETS + 'photos' + os.sep       # NNN.webp: thrift-shop photo of each piece


def piece_id(path):
    """The piece id (NNN) in a GLB's file name: the last three-digit number, as in 014.glb or work-014-legs.glb. Tools
    that pick the body pose by it fail on a name without one, instead of dressing pose C pants on the pose B body."""
    ids = re.findall(r'(?<!\d)\d{3}(?!\d)', os.path.basename(path))
    if not ids: raise SystemExit(f'{path}: name the file with the piece id (NNN), the body pose depends on it')
    return ids[-1]
