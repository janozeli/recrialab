import { describe, expect, test } from 'bun:test';
import { focusHeight, zoomStep } from './zoom';

const limits = { minRadius: 1.4, homeRadius: 3.88, homeY: .87, minY: .3, maxY: 1.5 };
const home = { radius: 3.88, targetY: .87 };
// Height on screen of a world height, in the camera's vertical frame (small-angle view along the horizontal).
const screen = (view: { radius: number; targetY: number }, y: number) => (y - view.targetY) / view.radius;

describe('zoom (button, wheel and pinch are one function)', () => {
  test('zooming in keeps the point under the finger in place on the screen', () => {
    for (const focus of [.4, 1.0, 1.4]) {
      const next = zoomStep(home, .7, focus, limits);
      expect(next.radius).toBeCloseTo(3.88 * .7, 6);
      expect(screen(next, focus)).toBeCloseTo(screen(home, focus), 6); // same place on the screen
      expect((focus - next.targetY) / (focus - home.targetY)).toBeCloseTo(.7, 6);
    }
  });
  test('does not aim at the middle: the head and the feet pull the aim their way', () => {
    expect(zoomStep(home, .5, 1.6, limits).targetY).toBeGreaterThan(1.2);
    expect(zoomStep(home, .5, .2, limits).targetY).toBeLessThan(.6);
  });
  test('stays between the near and far limits and inside the figure', () => {
    let v = home;
    for (let i = 0; i < 40; i++) v = zoomStep(v, .8, 2.5, limits);
    expect(v.radius).toBe(1.4); expect(v.targetY).toBeLessThanOrEqual(1.5);
    for (let i = 0; i < 40; i++) v = zoomStep(v, .8, -1, limits);
    expect(v.targetY).toBeGreaterThanOrEqual(.3);
  });
  test('zooming all the way out always lands on the full body, wherever it zoomed in', () => {
    for (const focus of [.2, .9, 1.7]) {
      let v = home;
      for (let i = 0; i < 6; i++) v = zoomStep(v, .8, focus, limits);
      for (let i = 0; i < 30 && v.radius < 3.88; i++) v = zoomStep(v, 1.15, focus, limits);
      expect(v).toEqual(home);
    }
  });
  test('the screen point is turned into the height it shows', () => {
    // Camera at 1.0 m looking at 0.87 m from 3.88 m: the middle of the screen shows the aim.
    expect(focusHeight(1.0, .87, 3.88, 30, 0)).toBeCloseTo(.87, 2);
    expect(focusHeight(1.0, .87, 3.88, 30, 1)).toBeGreaterThan(1.8);
    expect(focusHeight(1.0, .87, 3.88, 30, -1)).toBeLessThan(0);
  });
});
