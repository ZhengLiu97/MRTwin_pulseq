/*
MatlabIO.h

Class for Matlab communication

MRIzero Project

kai.herz@tuebingen.mpg.de
*/

#include <matrix.h>
#include <mex.h>
#include "BlochSimulator.h"


void ReadMATLABInput(int nrhs, const mxArray *prhs[], ReferenceVolume* refVol, ExternalSequence* seq, uint32_t& totalNumberOfADCSamples, uint32_t& numberOfSpins)
{
	if (nrhs < 2){
		mexErrMsgIdAndTxt("MRIzero:ReadMATLABInput:nrhs",
			"Three Inputs required: RefVolume and PulseSeq filename"); 
	}

	//Input 1: 3d Ref volume NxMx3
	// (:,:,1): Proton Density
	// (:,:,2): T1
	// (:,:,3): T2
	mwSize numDims = mxGetNumberOfDimensions(prhs[0]);
	if (numDims != 3)
	{
		mexErrMsgIdAndTxt("MRIzero:ReadMATLABInput:rrhs",
			"Input Volume must be 3 dimensional");
	}
	const mwSize* dims = mxGetDimensions(prhs[0]);
	if (dims[2] != 3)
	{
		mexErrMsgIdAndTxt("MRIzero:ReadMATLABInput:rrhs",
			"Input Volume must include PD, T1 and T2");
	}
	int nCols = dims[0];
	int nRows = dims[1];

	if (nCols != nRows){
		mexErrMsgIdAndTxt("MRIzero:ReadMATLABInput:rrhs", "Only MxM k-space possible yet (No MxN).");
	}

	if (nCols != COLS ) {
		mexErrMsgIdAndTxt("MRIzero:ReadMATLABInput:rrhs", "32 rows/cols work here.");
	}

	//get the data for the reference volume from the matlab pointer and store it in the eigen matrix class
	refVol->AllocateMemory(nRows, nCols);
	double * pData = mxGetPr(prhs[0]);
	double t1, t2;
	for (int x = 0; x < nCols; x++){
		for (int y = 0; y < nRows; y++){
			refVol->SetProtonDensityValue(y, x, pData[x + y*nCols + 0 * (nCols*nRows)]);
			t1 = pData[x + y*nCols + 1 * (nCols*nRows)];
			t2 = pData[x + y*nCols + 2 * (nCols*nRows)];
			refVol->SetR1Value(y, x, t1 <= 0.0 ? 0.0 : 1.0 / t1);
			refVol->SetR2Value(y, x, t2 <= 0.0 ? 0.0 : 1.0 / t2);
		}
	}

	// Input 2: Filename of the pulseseq file
	const int charBufferSize = 2048;
	char tmpCharBuffer[charBufferSize];
	// gete filename from matlab
	mxGetString(prhs[1], tmpCharBuffer, charBufferSize);
	std::string seqFileName = std::string(tmpCharBuffer);
	//load the seq file
	if (!seq->load(seqFileName)) {
		mexErrMsgIdAndTxt("MRIzero:ReadMATLABInput:rrhs",
			"Seq filename not found");
	}

	// check if seq file is valid for simulation
	totalNumberOfADCSamples = 0;
	for (uint32_t nSample = 0; nSample < seq->GetNumberOfBlocks(); nSample++)
	{
		// get current event block
		SeqBlock* seqBlock = seq->GetBlock(nSample);
		//check if it consists arbitrary gradients
		if (seqBlock->isArbitraryGradient(0) || seqBlock->isArbitraryGradient(1)){
			mexErrMsgIdAndTxt("MRIzero:ReadMATLABInput:rrhs", "Arbitrary Gardient simulation is not implemented yet");
		}
		// try to get pixel size from seq file
		if (seqBlock->isADC())	{
			totalNumberOfADCSamples += seqBlock->GetADCEvent().numSamples;
        }
		delete seqBlock; // pointer gets allocate with new in the GetBlock() function
	}

	if (nrhs > 2)
	{
		double* tmpSpins = mxGetPr(prhs[2]);
		numberOfSpins = uint32_t(*tmpSpins);
		if (numberOfSpins != SPINS) {
			mexErrMsgIdAndTxt("MRIzero:ReadMATLABInput:rrhs", "Only 256 Spins are possible");
		}
	}
}


bool ReturnKSpaceToMATLAB(int nlhs, mxArray* plhs[], KSpaceEvents& kSpace)
{

	uint32_t numKSamples = kSpace.numberOfSamples;
	//init and set the matlab pointer

	plhs[0] = mxCreateDoubleMatrix(1, numKSamples, mxCOMPLEX);
	plhs[1] = mxCreateDoubleMatrix(2, numKSamples, mxREAL);
	double* realSample = mxGetPr(plhs[0]);
	double* imagSample = mxGetPi(plhs[0]);
	double* gradientsAtSample = mxGetPr(plhs[1]);

	//copy kspace to matlab
	for (uint32_t sample = 0; sample < numKSamples; sample++){
		realSample[sample] = kSpace.kSample[sample].real;
		imagSample[sample] = kSpace.kSample[sample].imag;
		gradientsAtSample[sample*2] = kSpace.kX[sample];
		gradientsAtSample[sample*2+1] = kSpace.kY[sample];
	}
	return true;
}