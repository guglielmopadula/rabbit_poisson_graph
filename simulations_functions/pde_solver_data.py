import numpy as np
import ufl
from dolfinx import fem, io, mesh, plot
from ufl import ds, dx, grad, inner
from dolfinx.io import XDMFFile
from mpi4py import MPI
from petsc4py.PETSc import ScalarType
import time
from dolfinx.fem import FunctionSpace
import pyvista
from mpi4py import MPI
from dolfinx import mesh
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import DotProduct, WhiteKernel
import tetgen
import meshio
from tqdm import trange
from scipy.interpolate import RBFInterpolator

def volume_2_x(mesh):
    shape=mesh.shape
    mesh=mesh.reshape(-1,mesh.shape[-3],mesh.shape[-2],mesh.shape[-1])
    tmp=np.sum(np.sum(mesh[:,:,:,0],axis=2)*(np.linalg.det(mesh[:,:,1:,1:]-np.expand_dims(mesh[:,:,0,1:],2))/6),axis=1)
    return tmp.reshape(shape[:-3])


def calculate_simulation(name,bary,write=True):
    start=time.time()
    mymesh=meshio.read(name+".stl")
    print(volume_2_x(mymesh.points[mymesh.cells_dict["triangle"]]))
    tgen = tetgen.TetGen(mymesh.points,mymesh.cells_dict["triangle"])
    nodes, elem = tgen.tetrahedralize(quality=False,nobisect=False,fixedvolume=0.001,steinerleft=200000)
    nodes=nodes-np.min(nodes,axis=0)
    gdim = 3
    shape = "tetrahedron"
    degree = 1
    cell = ufl.Cell(shape, geometric_dimension=gdim)
    domain = ufl.Mesh(ufl.VectorElement("Lagrange", cell, degree))
    domain = mesh.create_mesh(MPI.COMM_WORLD, elem, nodes, domain)
    V = FunctionSpace(domain, ("CG", 1))
    uD = fem.Function(V)
    uD.interpolate(lambda x: np.exp(-((x[0]-bary[0])**2 + (x[1]-bary[1])**2+(x[2]-bary[2])**2)))
    tdim = domain.topology.dim
    fdim = tdim - 1
    domain.topology.create_connectivity(fdim, tdim)
    boundary_facets = mesh.exterior_facet_indices(domain.topology)
    boundary_dofs = fem.locate_dofs_topological(V, fdim, boundary_facets)
    bc = fem.dirichletbc(uD, boundary_dofs)
    #boundary_facets = mesh.locate_entities_boundary(domain, dim=fdim, marker=lambda x:np.isclose(x[2], 0.0))   
    #boundary_dofs = fem.locate_dofs_topological(V=V, entity_dim=fdim, entities=boundary_facets)
    #bc = fem.dirichletbc(value=ScalarType(0), dofs=boundary_dofs, V=V)
    u = ufl.TrialFunction(V)
    v = ufl.TestFunction(V) 
    f = fem.Function(V)
    f.interpolate(lambda x: np.exp(-((x[0]-bary[0])**2 + (x[1]-bary[1])**2+(x[2]-bary[2])**2)))
    a = ufl.dot(ufl.grad(u), ufl.grad(v)) * ufl.dx
    L = f * v * ufl.dx
    energy=fem.form(u* ufl.dx)
    problem = fem.petsc.LinearProblem(a, L, bcs=[bc], petsc_options={"ksp_type": "preonly", "pc_type": "lu"})
    uh = problem.solve()    
    value=fem.assemble.assemble_scalar(energy)
    u_val=uh.x.array
    if write:
        with io.XDMFFile(domain.comm, "simulations/"+name+".xdmf", "w") as xdmf:
            xdmf.write_mesh(domain)
            xdmf.write_function(uh)
    end=time.time()
    print(end-start)
    return value,u_val

if __name__=="__main__":
    np.random.seed(0)
    NUM_SAMPLES=600
    mymesh=meshio.read("data/bunny_{}.stl".format(0))
    print(np.min(mymesh.points))
    bary=np.mean(mymesh.points,axis=0)
    value,uh=calculate_simulation("data/bunny_{}".format(0),bary)
    energy_data=np.zeros(NUM_SAMPLES)
    u_data=np.zeros((NUM_SAMPLES,len(uh)))
    energy_data[0]=value
    u_data[0]=uh

    for i in trange(1,NUM_SAMPLES):
        value,uh=calculate_simulation("data/bunny_{}".format(i),bary)
        energy_data[i]=value
        u_data[i]=uh

    np.save("simulations/data/energy_data.npy",energy_data)
    np.save("simulations/data/u_data.npy",u_data)