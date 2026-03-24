import { Box, Typography } from '@mui/material';
import { AutoAwesome } from '@mui/icons-material';
import { useTranslation } from 'react-i18next';

interface LogoProps {
  size?: 'sm' | 'md' | 'lg';
  showText?: boolean;
}

export default function Logo({ size = 'md', showText = true }: LogoProps) {
  const { t } = useTranslation();
  const iconSizes = { sm: 20, md: 26, lg: 36 };
  const textVariants = { sm: 'body2', md: 'h6', lg: 'h4' } as const;

  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
      <Box
        sx={{
          width: iconSizes[size] + 12,
          height: iconSizes[size] + 12,
          borderRadius: '30%',
          background: 'linear-gradient(135deg, #e94560 0%, #0f3460 100%)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
        }}
      >
        <AutoAwesome sx={{ fontSize: iconSizes[size], color: '#fff' }} />
      </Box>
      {showText && (
        <Typography
          variant={textVariants[size]}
          fontWeight={700}
          sx={{ letterSpacing: '-0.02em', lineHeight: 1 }}
        >
          {t('appName')}
        </Typography>
      )}
    </Box>
  );
}
