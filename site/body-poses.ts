/** The two poses of the neutral body: B (default) and C, legs apart for the wide pants of POSE_C_BOTTOM_IDS. */
import bodyBUrl from './assets/body/pose-b.glb';
import bodyCUrl from './assets/body/pose-c.glb';
import registry from './assets/body/poses.json';

export type BodyPose = 'B' | 'C';
export const BODY_POSES: Record<BodyPose, { url: string; hash: string }> = {
  B: { url: bodyBUrl, hash: registry.poses.B.hash },
  C: { url: bodyCUrl, hash: registry.poses.C.hash },
};
export const POSE_C_BOTTOM_IDS: readonly string[] = registry.poseCBottomIds;
const cBottoms = new Set(POSE_C_BOTTOM_IDS);

/** Pose follows only the selected bottom. Removing it restores the original B pose. */
export function bodyPoseForBottom(id?: string | null): BodyPose {
  return id != null && cBottoms.has(id) ? 'C' : 'B';
}
