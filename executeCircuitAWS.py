from braket.circuits import Circuit, Gate, Observable
from braket.circuits import circuit
from braket.devices import LocalSimulator
from braket.aws import AwsDevice
import numpy as np
import math
import matplotlib.pyplot as plt
from math import pi
from fractions import Fraction
from math import gcd # greatest common divisor
import boto3
from braket.circuits import Circuit
from braket.devices import LocalSimulator
from braket.aws import AwsDevice
import time
import os
import json

def least_busy_backend_aws(qb):
    qpu_machine_names = AwsDevice.get_devices(statuses=['ONLINE'])
    print(qpu_machine_names)
    least_busy = None
    least_busy_tasks = 0
    for machine in qpu_machine_names:
        device = AwsDevice(machine.arn)
        device_task = device.queue_depth().quantum_tasks
        if device.properties.paradigm.qubitCount >= qb:
            if least_busy == None:
                least_busy = device
                least_busy_tasks = device_task
            elif device_task < least_busy_tasks:
                least_busy = device
                least_busy_tasks = device_task

    return least_busy
        

def recover_task_result(task_load):
    # recover task
    sleep_times = 0
    while sleep_times < 100000:
        status = task_load.state()
        print('Status of (reconstructed) task:', status)
        print('\n')
        # wait for job to complete
        # terminal_states = ['COMPLETED', 'FAILED', 'CANCELLED']
        if status == 'COMPLETED':
            # get results
            return task_load.result()
        else:
            time.sleep(1)
            sleep_times = sleep_times + 1
    print("Quantum execution time exceded")
    return None

def runAWS(machine, circuit, shots, s3_folder):
    x = int(shots)

    if machine=="local":
        device = LocalSimulator()
        result = device.run(circuit, shots=x).result()
        counts = result.measurement_counts
        print(counts)
        return counts
        
    device = AwsDevice(machine)

    if "sv1" not in machine and "tn1" not in machine:
        task = device.run(circuit, s3_folder, shots=x, poll_timeout_seconds=5 * 24 * 60 * 60) # Hacer lo mismo que con ibm para recuperar los resultados, guardar el id, usuarios... y despues en el scheduler, al iniciarlo, buscar el el bucket s3 si están los resultados, si no, esperar a que lleguen
        counts = recover_task_result(task).measurement_counts
        return counts
    else:
        task = device.run(circuit, s3_folder, shots=x)
        counts = task.result().measurement_counts
        return counts
