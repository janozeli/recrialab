"""Where the published assets live (site/assets/)."""
import os

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'site', 'assets') + os.sep
GARMENTS = ASSETS + 'garments' + os.sep   # NNN.glb, one per piece
BODY = ASSETS + 'body' + os.sep           # pose-b.glb, pose-c.glb and poses.json
MASKS = ASSETS + 'masks' + os.sep         # pose-b/NNN.json, pose-c/NNN.json: body triangles hidden under each piece
LAYERS = ASSETS + 'layers' + os.sep       # NNN.json: top-over-bottom tables, one per bottom
PHOTOS = ASSETS + 'photos' + os.sep       # NNN.webp: thrift-shop photo of each piece
