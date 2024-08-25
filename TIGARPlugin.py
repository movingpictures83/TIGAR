#!/usr/bin/env python

######################################################
# Import packages needed
import argparse
import multiprocessing
import sys

from time import time

import numpy as np
import pandas as pd

# For OLS and Logistics regression
import statsmodels.api as sm
from scipy import stats
stats.chisqprob = lambda chisq, df: stats.chi2.sf(chisq, df)

class MyArgs:
    def __init__(self):
        self.TIGAR_dir = ""
        self.geneexp_path = ""
        self.ped_path = ""
        self.pedinfo_path = ""
        self.method = ""
        self.thread = 1
        self.out_dir = ""
        self.out_twas_file = "out_tigar"

############################################################
# time calculation
#start_time = time()

##########################################################
# parse input arguments
#parser = argparse.ArgumentParser(description='Asso Study 01')

# Specify tool directory
#parser.add_argument('--TIGAR_dir' ,type=str)

# Gene annotation and Expression level file
#parser.add_argument('--gene_exp' ,type=str ,dest='geneexp_path')

# PED file path 
#parser.add_argument('--PED' ,type=str ,dest='ped_path')

# Association Information file path
#parser.add_argument('--PED_info' ,type=str ,dest='pedinfo_path')

# Method to use for regression
#parser.add_argument('--method' ,type=str)

# number of thread
#parser.add_argument('--thread' ,type=int)

# output dir
#parser.add_argument('--out_dir' ,type=str)

# output file
#parser.add_argument('--out_twas_file' ,type=str)


#args = parser.parse_args()
#sys.path.append(args.TIGAR_dir)

##################################################
# Import TIGAR functions, define other functions
import plugins.TIGAR.TIGAR.TIGARutils as tg

# For single phenotype
def regression_single(method,X,Y,Annot_df: pd.DataFrame,target):
 Result = Annot_df.copy()

 # add intercept column for design matrix
 newX = sm.add_constant(X)
 
 # regression
 if method=='OLS':
  lm = sm.OLS(Y,newX).fit(disp=0)
  Result['R2'] = lm.rsquared
  
 elif method=='Logit':
  lm = sm.Logit(Y,newX).fit(disp=0)
  Result['R2'] = lm.prsquared

 Result['BETA'] = lm.params.get(target)
 Result['BETA_SE'] = lm.bse.get(target)
 Result['T_STAT'] = lm.tvalues.get(target)
 Result['PVALUE'] = lm.pvalues.get(target)
 Result['N'] = len(X)
 
 return Result

# For multiple phenotype
def regression_multi(X,Y,Annot_df: pd.DataFrame):
 Result = Annot_df.copy()

 lm = sm.OLS(Y,X).fit(disp=0)

 Result['R2'] = lm.rsquared
 Result['F_STAT'] = lm.fvalue
 Result['PVALUE'] = lm.f_pvalue
 Result['N'] = len(X)
 
 return Result

# Single Phenotype
@tg.error_handler
def thread_single(num):
 target = TargetID[num]

 target_data = PEDExp[[*pheno,*cov,target]].dropna(axis=0, how='any')
 target_annot = Annot.iloc[[num]]

 X = target_data[[*cov, target]]
 Y = target_data[pheno]

 Result = regression_single(args.method,X,Y,target_annot,target)

 Result.to_csv(
  out_twas_path,
  sep='\t',
  header=None,
  index=None,
  mode='a')

# Multiple Phenotype
@tg.error_handler
def thread_multi(num):
 target = TargetID[num]
 target_data = Resid_Exp[[target, *pheno]].dropna(axis=0, how='any')
 target_annot = Annot.iloc[[num]]

 X = target_data[pheno]
 Y = target_data[target]

 Result = regression_multi(X,Y,target_annot)

 Result.to_csv(
  out_twas_path,
  sep='\t',
  header=None,
  index=None,
  mode='a')

import PyIO
import PyPluMA
class TIGARPlugin:
 def input(self, inputfile):
  self.parameters = PyIO.readParameters(inputfile)

 def run(self):
     pass
 def output(self, outputfile):
  global args
  global out_twas_path
  args = MyArgs()
  args.geneexp_path = PyPluMA.prefix()+"/"+self.parameters["gene_exp"]
  args.ped_path = PyPluMA.prefix()+"/"+self.parameters["PED"]
  args.pedinfo_path = PyPluMA.prefix()+"/"+self.parameters["PED_info"]
  args.method = self.parameters["method"]
  #args.thread = int(self.parameters["thread"])
  args.out_dir = outputfile
  args.out_twas_file = "output.twas.txt"
 
  ###########################################################
  # Print input arguments
  # out_twas_path = args.out_dir + '/indv_' + args.method + '_assoc.txt'
  out_twas_path = args.out_dir + '/' + args.out_twas_file

  print(
  '''********************************
  Input Arguments
  Predicted GReX data file: {geneexp_path}
  PED phenotype/covariate data file: {ped_path}
  PED information file: {pedinfo_path}
  Regression model used for association test: {method}
  Number of threads: {thread}
  Output directory: {out_dir}
  Output TWAS results file: {out_path}
  ********************************'''.format(**args.__dict__, out_path = out_twas_path))

  # tg.print_args(args)

  ############################################################

  # get sampleIDs, ped column info, expression file info
  global pheno
  global cov
  global Annot
  sampleID, sample_size, exp_info, ped_cols, n_pheno, pheno, cov = tg.sampleid_startup(**args.__dict__)
  print('Phenotypes to be studied: ' + ', '.join(pheno) + '\n')
  print('Covariates to be used: ' + ', '.join(cov) + '\n')

  print('Reading gene expression/annotation data.\n')
  global TargetID
  global PEDExp
  AnnotExp, TargetID, n_targets = tg.read_gene_annot_exp(**exp_info)

  # Read in PED file
  PED = pd.read_csv(args.ped_path,sep='\t',usecols=['IND_ID', *ped_cols])
  PED = PED[PED.IND_ID.isin(sampleID)]
  PED = tg.optimize_cols(PED)

  # get separate Annot, Exp dataframes
  Exp = (AnnotExp[sampleID]).T
  Exp.columns = TargetID
  Exp['IND_ID'] = Exp.index
  Exp = Exp.reset_index(drop=True)

  Annot = AnnotExp[AnnotExp.columns[0:5]]

  ###################################################
  # Thread Process

  if n_pheno == 1:
   PEDExp = PED.merge(Exp,left_on='IND_ID',right_on='IND_ID',how='outer').drop(columns=['IND_ID'])

   # output columns to dataframe
   out_cols = ['CHROM','GeneStart','GeneEnd','TargetID','GeneName','R2','BETA','BETA_SE','T_STAT','PVALUE','N'] 
   pd.DataFrame(columns=out_cols).to_csv(out_twas_path,sep='\t',header=True,index=None,mode='w')

   pool = multiprocessing.Pool(args.thread)
   pool.imap(thread_single,[num for num in range(n_targets)])
   pool.close()
   pool.join()

  elif n_pheno > 1:
   Resid = PED[['IND_ID']].copy()
  
   for i in range(n_pheno):
    Resid[pheno[i]] = sm.OLS(PED[pheno[i]],sm.add_constant(PED[cov])).fit().resid.values

   Resid_Exp = Resid.merge(Exp,left_on='IND_ID',right_on='IND_ID',how='outer').drop(columns=['IND_ID'])

   # output columns to dataframe
   out_cols = ['CHROM','GeneStart','GeneEnd','TargetID','GeneName','R2','F_STAT','PVALUE','N']   
   pd.DataFrame(columns=out_cols).to_csv(out_twas_path,sep='\t',header=True,index=None,mode='w')
  
   pool = multiprocessing.Pool(args.thread)
   pool.imap(thread_multi,[num for num in range(n_targets)])
   pool.close()
   pool.join()
  print('Done.')




