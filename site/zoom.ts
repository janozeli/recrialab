/** One zoom for the button, the wheel and the pinch (Lucas, 12/11/2026: "o botão tem um comportamento, zoom manual tem
 * outro, e o zoom é muito centralizado no meio"). Zooming in keeps the point under the finger or cursor where it is on
 * the screen; zooming out walks the aim back to the full body, which it reaches at the far limit. */
export type ZoomView = { radius: number; targetY: number };
export type ZoomLimits = { minRadius: number; homeRadius: number; homeY: number; minY: number; maxY: number };

export function zoomStep(view: ZoomView, factor: number, focusY: number, limits: ZoomLimits): ZoomView {
  const { minRadius, homeRadius, homeY, minY, maxY } = limits;
  const radius = Math.min(homeRadius, Math.max(minRadius, view.radius * factor));
  let targetY: number;
  // At the near limit, zooming in on another point slides the aim there, as if the zoom had gone on.
  if (radius === view.radius && factor < 1 && radius === minRadius) targetY = focusY + (view.targetY - focusY) * factor;
  else if (radius === view.radius) return view;
  else if (radius < view.radius) targetY = focusY + (view.targetY - focusY) * (radius / view.radius);
  else targetY = homeY + (view.targetY - homeY) * ((homeRadius - radius) / (homeRadius - view.radius));
  return { radius, targetY: Math.min(maxY, Math.max(minY, targetY)) };
}

/** Height where the ray through the screen point `ndcY` (-1 bottom, 1 top) meets the upright plane through the aim. */
export function focusHeight(cameraY: number, targetY: number, radius: number, fovDeg: number, ndcY: number): number {
  const pitch = Math.asin((targetY - cameraY) / radius);
  const ray = pitch + Math.atan(ndcY * Math.tan(fovDeg * Math.PI / 360));
  const horizontal = radius * Math.cos(pitch);
  return cameraY + horizontal * Math.tan(ray);
}
