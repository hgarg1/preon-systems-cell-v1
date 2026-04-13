# Biological Implementation Summary

## Scope

This repository implements a simplified, glucose-centric, prokaryote-like cell simulation. The model tracks one cell in a coarse environment using discrete-time state updates. It is biology-inspired rather than a literal biochemical simulator.

## Implemented Biology

The implemented state consists of:

- Cell energy pools: ATP and ADP
- Cytosol metabolites: glucose, pyruvate, acetyl-CoA, NADH/NAD+, FADH2/FAD, CO2, and membrane gradient
- Structural state: membrane integrity and glucose transporter density
- Bulk state: biomass, waste, alive/dead, and division count
- Spatial state: 3D position (`x`, `y`, `z`)
- Environment state: glucose concentration, generic electron acceptor concentration, basal targets, and toxicity

Representative v2 state:

```python
class CytosolState(BaseConfigModel):
    glucose: float = Field(ge=0)
    pyruvate: float = Field(ge=0)
    nadh: float = Field(ge=0)
    acetyl_coa: float = Field(ge=0)
    nad_plus: float = Field(ge=0)
    fad: float = Field(ge=0)
    fadh2: float = Field(ge=0)
    co2: float = Field(ge=0)
    membrane_gradient: float = Field(ge=0)


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
- Electron acceptor maintenance: the generic terminal acceptor replenishes toward a basal level
- Passive membrane transport: glucose moves down its concentration gradient into the cytosol
- Glycolysis: cytosolic glucose is converted with exact net stoichiometry:
  `1 glucose -> 2 pyruvate + 2 ATP + 2 NADH`
- Pyruvate oxidation: `pyruvate + NAD+ -> acetyl-CoA + CO2 + NADH`
- TCA cycle: `acetyl-CoA + 3 NAD+ + FAD + ADP -> 2 CO2 + 3 NADH + FADH2 + ATP`
- Electron transport: NADH and FADH2 are oxidized using the generic terminal acceptor to build membrane gradient
- Oxidative phosphorylation: membrane gradient and ADP are converted into ATP
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
- Glycolysis, pyruvate oxidation, TCA, electron transport, and oxidative phosphorylation are modeled as net reactions, not as enzyme-by-enzyme intermediates
- Electron transport uses a generic terminal acceptor instead of oxygen-specific chemistry
- Waste, toxicity, growth, repair, and movement remain coarse-grained system-level processes

Not implemented:

- Receptor occupancy or state-transition transporters
- Fermentation, oxygen-specific respiration chemistry, or detailed electron transport complexes
- DNA, RNA, proteins, gene regulation, signaling networks, or organelles
- Osmotic balance, pH, temperature, or multicellular behavior

## Default Scenario Depth

The bundled default scenario instantiates one cell in one environment with:

- external glucose at a maintained basal level
- passive diffusion across the membrane
- cytosolic glucose, pyruvate, acetyl-CoA, NADH/NAD+, FADH2/FAD, CO2, and membrane gradient pools
- glycolysis capped per step
- coarse downstream respiration caps and carrier-gradient yields
- existing maintenance, repair, growth, movement, and toxicity rules

Representative default scenario excerpt:

```yaml
version: 2
environment:
  glucose_concentration: 24.0
  basal_glucose_level: 24.0
  glucose_replenishment_rate: 0.9
  electron_acceptor_concentration: 24.0
  basal_electron_acceptor_level: 24.0
  electron_acceptor_replenishment_rate: 0.9
transport:
  passive_diffusion_rate: 2.6
metabolism:
  glucose_processing_cap_per_step: 2.1
  pyruvate_oxidation_cap_per_step: 2.0
  tca_cycle_cap_per_step: 2.0
  electron_transport_cap_per_step: 4.0
  oxidative_phosphorylation_cap_per_step: 4.0
cell:
  cytosol:
    glucose: 1.2
    pyruvate: 0.0
    nadh: 0.0
    acetyl_coa: 0.0
    nad_plus: 10.0
    fad: 4.0
    fadh2: 0.0
    co2: 0.0
    membrane_gradient: 0.0
  glucose_transporter_density: 1.1
```
