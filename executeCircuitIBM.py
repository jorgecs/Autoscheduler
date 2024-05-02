#!/usr/bin/env python
# coding: utf-8

# import libraries
import numpy as np
import math
import matplotlib.pyplot as plt
from math import pi
from fractions import Fraction
from math import gcd
import time

# Importar las bibliotecas de Qiskit
from qiskit import QuantumCircuit, Aer, execute
from qiskit.visualization import plot_histogram
from qiskit.circuit.library import QFT, CU1Gate
from qiskit import transpile
from qiskit_ibm_provider import least_busy, IBMProvider
from time import sleep

def least_busy_backend_ibm(qb):
    provider = IBMProvider('ibm-q', 'open', 'main')
    backend = provider.backends(filters=lambda x: x.configuration().n_qubits >= qb and
                               not x.configuration().simulator and x.status().operational==True)
    backend = least_busy(backend)
    return backend

# Ejecutar el circuito
def runIBM(machine, circuit, shots):
    
    if machine == "local":
        backend = Aer.get_backend('qasm_simulator')
        x = int(shots)
        job = execute(circuit, backend, shots=x)
        result = job.result()
        # After the execution, delete in the file the line with that id, its no longer needed (we just need it because there is a possibility of the machine to stop working in the middle)
        counts = result.get_counts()
        #print(counts)
        #x, y = factor(counts)
        #return [x, y]
        return counts
    else:

        # Load your IBM Quantum account
        provider = IBMProvider()
        backend = provider.get_backend(machine)

        qc_basis = transpile(circuit, backend)
        x = int(shots)
        job = execute(qc_basis, backend, shots=x) #TODO almacenar el identificador de la ejecucion en in fichero por si la máquina se revienta. Cuando se inicie la API, comprueba ese fichero y recupera los circuitos para hacerles el unscheduler (deberia almacenar el identificador del circuito con los datos de los usuarios(id), qubits de cada usuario)
        id = job.job_id() # Get the job id
        # Write the id in a file, along with the users, and their qubit numbers
        result = job.result()
        counts = result.get_counts()
        print(counts)
        return counts
