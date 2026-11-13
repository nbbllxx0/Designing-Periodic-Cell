// 3D cell view: the preview boundary surface of the current design (voxel-centre mask from the backend's level-set
// evaluator, the same formulas as amm/geometry.py), as one cell or tiled 3 x 3 x 3.
import { useMemo } from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls } from "@react-three/drei";
import * as THREE from "three";
import { useStore } from "../store";
import { fmt } from "../physics";

function CellMesh({ tiled }: { tiled: boolean }) {
  const preview = useStore((s) => s.preview);
  const geo = useMemo(() => {
    if (!preview || !preview.faces.length) return null;
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(preview.vertices, 3));
    g.setIndex(preview.faces);
    g.translate(-0.5, -0.5, -0.5);
    g.computeVertexNormals();
    return g;
  }, [preview]);
  if (!geo) return null;
  const offs: [number, number, number][] = [];
  const r = tiled ? [-1, 0, 1] : [0];
  for (const x of r) for (const y of r) for (const z of r) offs.push([x, y, z]);
  return (
    <group>
      {offs.map((o) => (
        <mesh key={o.join(",")} geometry={geo} position={o}>
          <meshStandardMaterial color={o.every((v) => v === 0) ? "#5b8fd6" : "#8aa9cf"} metalness={0.15} roughness={0.55}
            flatShading />
        </mesh>
      ))}
      {!tiled && (
        <lineSegments>
          <edgesGeometry args={[new THREE.BoxGeometry(1, 1, 1)]} />
          <lineBasicMaterial color="#888" />
        </lineSegments>
      )}
    </group>
  );
}

export function CellView() {
  const tiled = useStore((s) => s.tiled);
  const setTiled = useStore((s) => s.setTiled);
  const preview = useStore((s) => s.preview);
  const summary = useStore((s) => s.summary);
  const cs = summary?.state.cell_size;
  return (
    <section className="panel view3d">
      <div className="panel-head">
        <h2>Cell {tiled ? "(tiled 3 x 3 x 3)" : ""}</h2>
        <span className="seg">
          <button className={!tiled ? "on" : ""} onClick={() => setTiled(false)}>cell</button>
          <button className={tiled ? "on" : ""} onClick={() => setTiled(true)}>tiled</button>
        </span>
      </div>
      <div className="canvas-wrap">
        <Canvas camera={{ position: tiled ? [3.9, 3.0, 4.5] : [1.75, 1.35, 2.05], fov: 40 }} gl={{ preserveDrawingBuffer: true }}
          key={tiled ? "t" : "c"}>
          <color attach="background" args={["#f4f6f9"]} />
          <ambientLight intensity={0.55} />
          <directionalLight position={[3, 5, 4]} intensity={1.1} />
          <directionalLight position={[-4, -2, -3]} intensity={0.35} />
          <CellMesh tiled={tiled} />
          <OrbitControls makeDefault enableDamping={false} />
        </Canvas>
        <div className="overlay muted small">
          {preview ? `${preview.kind}, preview n = ${preview.n}, solid fraction ${fmt(preview.density_preview, 3)}` : ""}
          {cs ? `; a = ${fmt(cs[0])} ${cs[1]}` : "; a unset"}
          <br />preview geometry, not the certified finite-cell voxelization
        </div>
      </div>
    </section>
  );
}
