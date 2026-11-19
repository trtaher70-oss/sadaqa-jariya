import React from 'react';
import {Composition} from 'remotion';
import {Ayah, AyahProps} from './Ayah';

export const Root: React.FC = () => (
  <Composition
    id="Ayah"
    component={Ayah}
    width={1080}
    height={1920}
    fps={30}
    durationInFrames={300}
    defaultProps={{hook: 'عنوان', kind: 'دعاء', audio: [], pages: [], total: 10, outroDur: 2.6, reciter: ''} as AyahProps}
    calculateMetadata={({props}) => ({durationInFrames: Math.round(props.total * 30)})}
  />
);
