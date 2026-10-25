import { PerspectiveCamera, Scene, Vector2, WebGLRenderer } from 'three';

/** Renders the image locally, without changing the camera or the resolution of the fitting room. */
export async function exportLookImage(
  renderer: WebGLRenderer,
  scene: Scene,
  camera: PerspectiveCamera,
  logo: HTMLImageElement,
  colors: { paper: string; pink: string; ink: string },
  label = '',
): Promise<Blob> {
  await logo.decode();
  const canvas = document.createElement('canvas');
  canvas.width = 1080;
  canvas.height = 1350;
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('2D canvas unavailable');

  const frame = { x: 32, y: 144, width: 1016, height: 1174 };
  ctx.fillStyle = colors.paper;
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  const logoWidth = 272;
  const logoHeight = logoWidth * logo.naturalHeight / logo.naturalWidth;
  ctx.drawImage(logo, (canvas.width - logoWidth) / 2, (frame.y - logoHeight) / 2, logoWidth, logoHeight);
  ctx.fillStyle = colors.pink;
  ctx.fillRect(frame.x, frame.y, frame.width, frame.height);

  ctx.save();
  ctx.beginPath();
  ctx.rect(frame.x, frame.y, frame.width, frame.height);
  ctx.clip();
  ctx.translate(canvas.width / 2, frame.y + frame.height * .46);
  ctx.fillStyle = colors.ink;
  ctx.globalAlpha = .07;
  for (let ray = 0; ray < 12; ray++) {
    ctx.rotate(Math.PI / 6);
    ctx.beginPath();
    ctx.moveTo(0, 0);
    ctx.lineTo(-180, -1800);
    ctx.lineTo(180, -1800);
    ctx.fill();
  }
  ctx.restore();

  ctx.fillStyle = colors.paper;
  ctx.strokeStyle = colors.ink;
  ctx.lineWidth = 4;
  ctx.beginPath();
  ctx.ellipse(canvas.width / 2, frame.y + frame.height * .9, frame.width * .25, frame.height * .04, -.05, 0, Math.PI * 2);
  ctx.fill();
  ctx.stroke();

  const size = renderer.getSize(new Vector2());
  const pixelRatio = renderer.getPixelRatio();
  // The file always uses the front view; turning the fitting room does not change the export.
  const exportCamera = new PerspectiveCamera(30, frame.width / frame.height, .1, 30);
  exportCamera.position.set(0, 1.15, 4.4);
  exportCamera.lookAt(0, 1, 0);
  try {
    renderer.setPixelRatio(1);
    renderer.setSize(frame.width, frame.height, false);
    // Rendering and copying in the same task avoid an empty PNG with preserveDrawingBuffer=false.
    renderer.render(scene, exportCamera);
    ctx.drawImage(renderer.domElement, frame.x, frame.y, frame.width, frame.height);
  } finally {
    renderer.setPixelRatio(pixelRatio);
    renderer.setSize(size.x, size.y, false);
    renderer.render(scene, camera);
  }
  ctx.strokeStyle = colors.ink;
  ctx.lineWidth = 4;
  ctx.strokeRect(frame.x, frame.y, frame.width, frame.height);
  if (label) {
    // Piece codes visible on the image itself, so curators can identify the look.
    ctx.font = '700 34px "Barlow Condensed", system-ui, sans-serif';
    ctx.textAlign = 'right';
    ctx.textBaseline = 'bottom';
    ctx.fillStyle = colors.ink;
    ctx.fillText(label, frame.x + frame.width - 24, frame.y + frame.height - 18);
  }
  return new Promise((resolve, reject) => canvas.toBlob(
    blob => blob ? resolve(blob) : reject(new Error('could not create the PNG')),
    'image/png',
  ));
}
