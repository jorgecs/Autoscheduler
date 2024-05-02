from urllib.parse import urlparse
import requests
import re
from executeCircuitIBM import runIBM
from executeCircuitAWS import runAWS
from divideResults import divideResults
from translator import get_ibm_individual, get_aws_individual
import math
import ast
from urllib.parse import unquote

class Autocomposer:
    def __init__(self, circuit, shots, machine, max_qubits, provider=None, s3_folder=None): #TODO max_qubits se deberia coger dependiendo de la maquina, no deberia ser un parametro de entrada (o sí si se quiere que el usuario tenga capacidad de cambiar cómo es la composicion)
       self.machine = machine
       self.max_qubits = max_qubits
       self.circuit = circuit
       self.shots = shots
       self.provider = provider
       self.s3_folder = s3_folder
       self.qc = None

    def compose(self):

        if 'algassert' in self.circuit:
            if self.provider == None:
                return "Provider not specified"
            qubits = self.get_qubits_url()
            if self.max_qubits < qubits:
                return "Circuit too large"
            shots,times = self.create_circuit_url(qubits)
        else: 
            qubits = self.get_qubits_circuit()
            if self.provider == 'aws' and self.s3_folder == None and self.machine != 'local':
                return "S3 Bucket not specified"
            if self.max_qubits < qubits:
                return "Circuit too large"
            shots,times = self.create_circuit_circuit(qubits)        

        counts = self.execute(shots)
        results = self.decompose(counts,shots,qubits,times)
        return results
    
    def get_qubits_url(self):
        fragment = urlparse(self.circuit).fragment
        circuit_str = fragment[len('circuit='):]
        circuit = ast.literal_eval(unquote(circuit_str))
        qubits = max(len(col) for col in circuit['cols'] if 1 not in col)
        return qubits
    
    def create_circuit_url(self, qubits):
        times =  self.max_qubits // qubits
        shots = math.ceil(self.shots / times)
        print(f"Qubits: {qubits}, Times: {times}, Shots: {shots}")
        self.qc = ""
        if self.provider == "ibm":
            for i in range(times):
                self.qc += get_ibm_individual(self.circuit,(i*qubits)) + '\n'
            self.qc = (
                "from numpy import pi\n"
                "import numpy as np\n"
                "from qiskit import execute, QuantumRegister, ClassicalRegister, QuantumCircuit, Aer\n"
                f"qreg_q = QuantumRegister({qubits*(times)}, 'q')\n"
                f"creg_c = ClassicalRegister({qubits*(times)}, 'c')\n"
                "circuit = QuantumCircuit(qreg_q, creg_c)\n"
                + self.qc
            )
        elif self.provider == "aws":
            for i in range(times):
                self.qc += get_aws_individual(self.circuit,(i*qubits)) + '\n'
            self.qc = (
                "from numpy import pi\n"
                "import numpy as np\n"
                "from collections import Counter\n"
                "from braket.circuits import Circuit\n"
                "circuit = Circuit()\n"
                + self.qc
            )

        return shots,times

    def get_qubits_circuit(self):
        try:
            parsed_url = urlparse(self.circuit)
            if parsed_url.netloc != "raw.githubusercontent.com":
                return "URL must come from a raw GitHub file", 400
            response = requests.get(self.circuit)
            response.raise_for_status()
            # Get the name of the file
        except requests.exceptions.RequestException as e:
            print(f"Error getting URL content: {e}")
            return "Invalid URL", 400
        
        circuit = response.text
        lines = circuit.split('\n')
        importAWS = next((line for line in lines if 'braket.circuits' in line), None)
        importIBM = next((line for line in lines if 'qiskit' in line), None)

        if importIBM:
            num_qubits_line = next((line for line in lines if '= QuantumRegister(' in line), None)
            num_qubits = int(num_qubits_line.split('QuantumRegister(')[1].split(',')[0].strip(')')) if num_qubits_line else None

            # Get the data before the = in the line that appears QuantumCircuit(...)
            file_circuit_name_line = next((line for line in lines if '= QuantumCircuit(' in line), None)
            file_circuit_name = file_circuit_name_line.split('=')[0].strip() if file_circuit_name_line else None
            # Get the name of the quantum register
            qreg_line = next((line for line in lines if '= QuantumRegister(' in line), None)
            qreg = qreg_line.split('=')[0].strip() if qreg_line else None
            # Get the name of the classical register
            creg_line = next((line for line in lines if '= ClassicalRegister(' in line), None)
            creg = creg_line.split('=')[0].strip() if creg_line else None
            # Remove all lines that don't start with file_circuit_name and don't include the line that has file_circuit_name.add_register and line not starts with // or # (comments)
            circuit = '\n'.join([line for line in lines if line.strip().startswith(file_circuit_name+'.') and 'add_register' not in line and not line.strip().startswith('//') and not line.strip().startswith('#')])

            circuit = '\n'.join([line.lstrip() for line in circuit.split('\n')])

            # Replace all appearances of file_circuit_name, qreg, and creg
            circuit = circuit.replace(file_circuit_name+'.', 'circuit.')
            circuit = circuit.replace(f'{qreg}[', 'qreg_q[')
            circuit = circuit.replace(f'{creg}[', 'creg_c[')
            # Create an array with the same length as the number of qubits initialized to 0 to count the number of gates on each qubit
            qubits = [0] * num_qubits
            for line in circuit.split('\n'): # For each line in the circuit
                if 'measure' not in line and 'barrier' not in line: #If the line is not a measure or a barrier
                    # Check the numbers after qreg_q and add 1 to qubits on that position. It should work with whings like circuit.cx(qreg_q[0], qreg_q[3]), adding 1 to both 0 and 3
                    # This adds 1 to the number of gates used on that qubit
                    for match in re.finditer(r'qreg_q\[(\d+)\]', line):
                        qubits[int(match.group(1))] += 1
            self.provider = "ibm"
            self.qc = circuit

        elif importAWS:
            file_circuit_name_line = next((line for line in lines if '= Circuit(' in line), None)
            file_circuit_name = file_circuit_name_line.split('=')[0].strip() if file_circuit_name_line else None

            # Remove all lines that don't start with file_circuit_name and don't include the line that has file_circuit_name.add_register and line not starts with // or # (comments)
            circuit = '\n'.join([line for line in lines if line.strip().startswith(file_circuit_name+'.') and not line.strip().startswith('//') and not line.strip().startswith('#')])

            circuit = circuit.replace(file_circuit_name+'.', 'circuit.')
            # Remove tabs and spaces at the beginning of the lines
            circuit = '\n'.join([line.lstrip() for line in circuit.split('\n')])

            # Create an array with the same length as the number of qubits initialized to 0 to count the number of gates on each qubit
            qubits = {}
            for line in circuit.split('\n'): # For each line in the circuit
                if 'barrier' not in line and 'circuit.' in line: #If the line is not a measure or a barrier
                    numbers = re.findall(r'\d+', line)
                    for elem in numbers:
                        if elem not in qubits:
                            qubits[elem] = 0
                        else:
                            qubits[elem] += 1
            num_qubits = len(qubits.values())
            self.provider = "aws"
            self.qc = circuit

        return num_qubits
    
    def create_circuit_circuit(self, qubits):
        times =  self.max_qubits // qubits
        shots = math.ceil(self.shots / times)
        print(f"Qubits: {qubits}, Times: {times}, Shots: {shots}")

        circuit = self.qc
        circuit += '\n'

        for i in range(times-1):
            edited_circuit = circuit
            # In the circuit, change all [...] to [...+(i*qubits)]
            if self.provider == "ibm":
                edited_circuit = re.sub(r'\[(\d+)\]', r'[\g<1>+' + f'{(i+1)*qubits}]', edited_circuit)
            elif self.provider == "aws":
                edited_circuit = re.sub(r'(\d+)', r'\g<1>+' + f'{(i+1)*qubits}', edited_circuit)
            self.qc += '\n' + edited_circuit  # Add newline before appending
        
        if self.provider == "ibm":
            self.qc = (
                "from numpy import pi\n"
                "import numpy as np\n"
                "from qiskit import execute, QuantumRegister, ClassicalRegister, QuantumCircuit, Aer\n"
                f"qreg_q = QuantumRegister({qubits*(times)}, 'q')\n"
                f"creg_c = ClassicalRegister({qubits*(times)}, 'c')\n"
                "circuit = QuantumCircuit(qreg_q, creg_c)\n"
                + self.qc
            )
        elif self.provider == "aws":
            self.qc = (
                "from numpy import pi\n"
                "import numpy as np\n"
                "from collections import Counter\n"
                "from braket.circuits import Circuit\n"
                "circuit = Circuit()\n"
                + self.qc
            )

        return shots,times

    def execute(self, shots):
        loc = {}

        exec(self.qc,globals(),loc)
        if self.provider == "ibm":
            counts = runIBM(self.machine,loc['circuit'],shots)
        elif self.provider == "aws":
            counts = runAWS(self.machine,loc['circuit'],shots,self.s3_folder)
        return counts

    def decompose(self, counts, shots, qubits, times):
        users = [0] * times
        circuit_name = [0] * times
        shots = [shots] * times
        qubits = [qubits] * times  
        results = divideResults(counts, shots, self.provider, qubits, users, circuit_name)
        circuit_results = {}

        for result in results:
            for key, value in result[(0, 0)].items():
                if key not in circuit_results:
                    circuit_results[key] = value
                else:
                    circuit_results[key] += value

        return circuit_results
    
    def get_qubits_machine(self):
        if provider == 'ibm':
            from qiskit_ibm_runtime import QiskitRuntimeService
            service = QiskitRuntimeService()
            service.backend('ibm_brisbane').configuration().n_qubits
        elif provider == 'aws':
            from braket.aws import AwsDevice
            device = AwsDevice("arn:aws:braket:::device/qpu/ionq/ionQdevice")
            device.properties.provider.device_parameters.qubit_count
        

if __name__ == "__main__":
    print("----------------AWS------------------")
    circuit = "https://algassert.com/quirk#circuit={'cols':[['H'],['•','X'],['Measure','Measure']]}"
    shots = 5000
    machine = "local"
    max_qubits = 4
    provider = "aws"
    autocomposer = Autocomposer(circuit, shots, machine, max_qubits, provider)
    results = autocomposer.compose()
    print('Results: ',results)
    print("-------------------")
    circuit = "https://raw.githubusercontent.com/jorgecs/pythonscripts/main/shor7xMOD15Circuit.py"
    max_qubits = 16
    autocomposer = Autocomposer(circuit, shots, machine, max_qubits)
    results = autocomposer.compose()
    print('Results: ',results)

    print("----------------IBM------------------")

    circuit = "https://algassert.com/quirk#circuit={'cols':[['H'],['•','X'],['Measure','Measure']]}"
    shots = 5000
    machine = "local"
    max_qubits = 4
    provider = 'ibm'
    autocomposer = Autocomposer(circuit, shots, machine, max_qubits,provider)
    results = autocomposer.compose()
    print('Results: ',results)
    print("-------------------")
    circuit = "https://raw.githubusercontent.com/jorgecs/CompositionCircuits/main/simon.py"
    max_qubits = 29
    autocomposer = Autocomposer(circuit, shots, machine, max_qubits)
    results = autocomposer.compose()
    print('Results: ',results)