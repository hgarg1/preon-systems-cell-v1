# Biological Implementation Summary

## Scope

This repository implements a simplified, glucose-centric, prokaryote-like cell simulation. The model tracks one cell in a coarse environment using discrete-time state updates. It is biology-inspired rather than a literal biochemical simulator.

## Implemented Biology

The implemented state consists of:

- Cell energy pools: ATP and ADP
- Cytosol metabolites: glucose, pyruvate, and NADH
- Structural state: membrane integrity and glucose transporter density
- Bulk state: biomass, waste, alive/dead, and division count
- Spatial state: 3D position (`x`, `y`, `z`)
- Environment state: glucose concentration, basal glucose target, and toxicity

Representative v2 state:

```python
class CytosolState(BaseConfigModel):
    glucose: float = Field(ge=0)
    pyruvate: float = Field(ge=0)
    nadh: float = Field(ge=0)


class CellState(BaseConfigModel):
    name: str
    energy: EnergyState
    cytosol: CytosolState
    waste: float = Field(ge=0)
    membrane_integrity: float = Field(ge=0, le=1)
    glucose_transporter_density: float = Field(ge=0)
    biomass: float = Field(ge=0)
```

The implemented processes are:

- Environment maintenance: external glucose replenishes toward a basal glucose level
- Passive membrane transport: glucose moves down its concentration gradient into the cytosol
- Glycolysis: cytosolic glucose is converted with exact net stoichiometry:
  `1 glucose -> 2 pyruvate + 2 ATP + 2 NADH`
- Maintenance: ATP is consumed each step
- Membrane damage and repair: integrity decays and can be repaired using ATP
- Growth and division: ATP can be invested into biomass, with simple threshold-based division
- Movement: the cell drifts through 3D space
- Termination: ATP depletion, starvation, membrane failure, or toxicity overload

Representative v2 transport and glycolysis logic:

```python
gradient = env.glucose_concentration - cell.cytosol.glucose
flux_cap = passive_diffusion_rate * glucose_transporter_density * membrane_factor * dt
imported = min(gradient, flux_cap, env.glucose_concentration)
```

```python
processed = min(cell.cytosol.glucose, glucose_processing_cap_per_step * dt)
cell.cytosol.glucose -= processed
cell.cytosol.pyruvate += processed * 2.0
cell.cytosol.nadh += processed * 2.0
cell.energy.atp += processed * 2.0
cell.energy.adp = max(cell.energy.adp - processed * 2.0, 0)
```

## Extent

The v2 engine now includes an explicit cytosol and named glucose metabolism products, but it remains coarse:

- Passive glucose transport is represented by a scalar transporter density, not binding kinetics
- Glycolysis is modeled as a net reaction, not as enzyme-by-enzyme intermediates
- Pyruvate and NADH accumulate in the cytosol and are not consumed downstream
- Waste, toxicity, growth, repair, and movement remain coarse-grained system-level processes

Not implemented:

- Receptor occupancy or state-transition transporters
- TCA cycle, fermentation, oxidative phosphorylation, or downstream pyruvate/NADH usage
- DNA, RNA, proteins, gene regulation, signaling networks, or organelles
- Osmotic balance, pH, temperature, or multicellular behavior

## Default Scenario Depth

The bundled default scenario instantiates one cell in one environment with:

- external glucose at a maintained basal level
- passive diffusion across the membrane
- cytosolic glucose, pyruvate, and NADH pools
- glycolysis capped per step
- existing maintenance, repair, growth, movement, and toxicity rules

Representative default scenario excerpt:

```yaml
version: 2
environment:
  glucose_concentration: 24.0
  basal_glucose_level: 24.0
  glucose_replenishment_rate: 0.9
transport:
  passive_diffusion_rate: 2.6
metabolism:
  glucose_processing_cap_per_step: 2.1
cell:
  cytosol:
    glucose: 1.2
    pyruvate: 0.0
    nadh: 0.0
  glucose_transporter_density: 1.1
```
