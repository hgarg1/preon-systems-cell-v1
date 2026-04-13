"use client";

import { useEffect, useRef } from "react";
import * as THREE from "three";

import type { LineageEdge, LineageNode } from "@/lib/api";

import { lineageColor } from "./format";

interface LineageSceneProps {
  nodes: LineageNode[];
  edges: LineageEdge[];
  selectedCellId: string | null;
  onSelectCell: (cellId: string) => void;
}

export function LineageScene({ nodes, edges, selectedCellId, onSelectCell }: LineageSceneProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !nodes.length) {
      return;
    }
    const canvasElement: HTMLCanvasElement = canvas;

    const renderer = new THREE.WebGLRenderer({ canvas: canvasElement, antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

    const scene = new THREE.Scene();
    scene.fog = new THREE.Fog(0x0d1512, 14, 34);

    const camera = new THREE.PerspectiveCamera(48, 1, 0.1, 100);
    camera.position.set(0, 5.8, 13.5);
    camera.lookAt(0, 0, 0);

    const root = new THREE.Group();
    scene.add(root);

    const ambient = new THREE.AmbientLight(0xffffff, 0.65);
    scene.add(ambient);

    const keyLight = new THREE.DirectionalLight(0x9fffc9, 2.2);
    keyLight.position.set(5, 7, 8);
    scene.add(keyLight);

    const fillLight = new THREE.PointLight(0xffd166, 1.2, 30);
    fillLight.position.set(-6, 2, 4);
    scene.add(fillLight);

    const positions = layoutNodes(nodes);
    const pickables: THREE.Mesh[] = [];

    const lineMaterial = new THREE.LineBasicMaterial({
      color: 0x8ff5c1,
      transparent: true,
      opacity: 0.36,
    });

    for (const edge of edges) {
      const source = positions.get(edge.source);
      const target = positions.get(edge.target);
      if (!source || !target) {
        continue;
      }
      const geometry = new THREE.BufferGeometry().setFromPoints([source, target]);
      root.add(new THREE.Line(geometry, lineMaterial));
    }

    for (const node of nodes) {
      const position = positions.get(node.id);
      if (!position) {
        continue;
      }
      const color = new THREE.Color(lineageColor(node.id, node.generation));
      const radius = node.id === selectedCellId ? 0.27 : 0.19;
      const geometry = new THREE.IcosahedronGeometry(radius, 3);
      const material = new THREE.MeshStandardMaterial({
        color,
        emissive: color.clone().multiplyScalar(node.id === selectedCellId ? 0.32 : 0.16),
        roughness: 0.42,
        metalness: 0.18,
      });
      const mesh = new THREE.Mesh(geometry, material);
      mesh.position.copy(position);
      mesh.userData.cellId = node.id;
      root.add(mesh);
      pickables.push(mesh);

      if (node.id === selectedCellId) {
        const ringGeometry = new THREE.TorusGeometry(radius + 0.12, 0.012, 8, 40);
        const ringMaterial = new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.82 });
        const ring = new THREE.Mesh(ringGeometry, ringMaterial);
        ring.position.copy(position);
        ring.rotation.x = Math.PI / 2;
        root.add(ring);
      }
    }

    const grid = new THREE.GridHelper(12, 12, 0x24423a, 0x1b302b);
    grid.position.y = -2.4;
    root.add(grid);

    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    let hovered: THREE.Mesh | null = null;

    function resize() {
      const { clientWidth, clientHeight } = canvasElement;
      const width = Math.max(clientWidth, 1);
      const height = Math.max(clientHeight, 1);
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
    }

    function updatePointer(event: PointerEvent) {
      const rect = canvasElement.getBoundingClientRect();
      pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
    }

    function onPointerMove(event: PointerEvent) {
      updatePointer(event);
      raycaster.setFromCamera(pointer, camera);
      const hit = raycaster.intersectObjects(pickables, false)[0]?.object as THREE.Mesh | undefined;
      if (hovered !== hit) {
        hovered = hit ?? null;
        canvasElement.style.cursor = hovered ? "pointer" : "default";
      }
    }

    function onClick(event: PointerEvent) {
      updatePointer(event);
      raycaster.setFromCamera(pointer, camera);
      const hit = raycaster.intersectObjects(pickables, false)[0]?.object as THREE.Mesh | undefined;
      const cellId = hit?.userData.cellId;
      if (typeof cellId === "string") {
        onSelectCell(cellId);
      }
    }

    let frame = 0;
    function animate() {
      frame = requestAnimationFrame(animate);
      root.rotation.y += 0.0025;
      renderer.render(scene, camera);
    }

    const observer = new ResizeObserver(resize);
    observer.observe(canvasElement);
    canvasElement.addEventListener("pointermove", onPointerMove);
    canvasElement.addEventListener("click", onClick);
    resize();
    animate();

    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      canvasElement.removeEventListener("pointermove", onPointerMove);
      canvasElement.removeEventListener("click", onClick);
      renderer.dispose();
      root.traverse((object) => {
        if ("geometry" in object && object.geometry instanceof THREE.BufferGeometry) {
          object.geometry.dispose();
        }
        if ("material" in object) {
          const material = object.material;
          if (Array.isArray(material)) {
            material.forEach((entry) => entry.dispose());
          } else if (material instanceof THREE.Material) {
            material.dispose();
          }
        }
      });
    };
  }, [edges, nodes, onSelectCell, selectedCellId]);

  return (
    <section className="overflow-hidden rounded-lg border border-white/10 bg-neutral-950/70">
      <div className="flex flex-col gap-2 border-b border-white/10 px-4 py-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-base font-medium text-white">Lineage map</h2>
          <p className="text-sm text-neutral-400">Depth color, selected node halo, and branch links.</p>
        </div>
        <div className="font-mono text-xs text-neutral-400">
          {nodes.length} cells / {edges.length} links
        </div>
      </div>
      <div className="relative h-[22rem]">
        {nodes.length ? (
          <canvas ref={canvasRef} className="h-full w-full" aria-label="3D lineage map" />
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-neutral-400">No lineage nodes</div>
        )}
      </div>
    </section>
  );
}

function layoutNodes(nodes: LineageNode[]): Map<string, THREE.Vector3> {
  const byGeneration = new Map<number, LineageNode[]>();
  for (const node of nodes) {
    byGeneration.set(node.generation, [...(byGeneration.get(node.generation) ?? []), node]);
  }

  const maxGeneration = Math.max(0, ...nodes.map((node) => node.generation));
  const positions = new Map<string, THREE.Vector3>();

  for (const [generation, generationNodes] of byGeneration.entries()) {
    const radius = 1.2 + generation * 1.35;
    const y = (maxGeneration - generation) * 0.75 - 1.2;
    generationNodes.forEach((node, index) => {
      const angle = (index / Math.max(generationNodes.length, 1)) * Math.PI * 2 + generation * 0.48;
      positions.set(
        node.id,
        new THREE.Vector3(Math.cos(angle) * radius, y, Math.sin(angle) * radius),
      );
    });
  }

  return positions;
}
